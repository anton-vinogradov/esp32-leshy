#!/usr/bin/env python3
"""Retain/check non-identifying evidence for virgin-device denied-entry UX.

Raw serial, USB identifiers and backup images stay private in work/outputs.
The retained projection contains only explicit UI actions and allowlisted state.
This delta does not claim unlocked radio operation or physical keypad/touch HIL.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'tests/hil/evidence/board-03-lock-entry-1.0.0-dev.379.json'
VERSION = '1.0.0-dev.379'
SOURCE = '266fea8eb399a9a82ac4d4b0ab4db3d14ffd822a'
APP = '74137ccd50b15bb503ce57fe875ec10cfffb02501d373ae51716376d0b0c9519'
ELF = '5ac2f1d03bbb70cdeaa50d2bd96d862a99c388c48e1ce302ba134f25a25694a1'
UI_FIELDS = ('page', 'parent_page', 'selected_id', 'selection', 'device_selection',
             'runtime_event', 'runtime_owner', 'lease_mask', 'ui_full_repaints',
             'ui_delta_repaints', 'survey_product_store_open_attempted',
             'survey_product_store_bytes_written')
LOCK_FIELDS = ('status', 'credential_generation', 'protected_access', 'worker_active',
               'radio_touched', 'persistence_fixture_active', 'failed_attempts', 'failure')
INPUT_FIELDS = ('read_errors', 'queue_drops')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def project(value, fields):
    return {key: value[key] for key in fields}


def retain(raw_path):
    raw = json.loads(raw_path.read_text())
    require(raw['status'] == 'passed', 'raw HIL did not pass')
    live = False
    samples = []
    metrics = None
    for sample in raw['samples']:
        command, value = sample['command'], sample['value']
        if command == 'metrics' and value['version'] == VERSION:
            live = True
            metrics = project(value, ('version', 'app_elf_sha256', 'heap_free', 'heap_min_free'))
        elif live:
            fields = (LOCK_FIELDS if command == 'device-lock.state' else INPUT_FIELDS
                      if command == 'input.state' else UI_FIELDS)
            require(command in ('device-lock.state', 'input.state', 'ui.state') or
                    command in ('ui.key up', 'ui.key down', 'ui.key left', 'ui.key right', 'ui.key select'),
                    'unexpected command in entry-only delta')
            samples.append(dict(command=command, value=project(value, fields)))
    frames = {name: dict(pixel_sha256=value['pixel_sha256'], png_sha256=value['png_sha256'],
                         state=project(value['state'], UI_FIELDS))
              for name, value in raw['frames'].items()}
    result = dict(schema='leshy.device_lock.entry_remedy.hil.v1', status='passed', board_id='board-03',
                  source_commit=raw['source_commit'], firmware_version=raw['firmware_version'],
                  app_sha256=raw['app_sha256'], app_elf_sha256=raw['app_elf_sha256'],
                  raw_evidence_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                  runner_sha256=hashlib.sha256((ROOT / 'work/board03_lock_entry.py').read_bytes()).hexdigest(),
                  metrics=metrics, checks=raw['checks'], samples=samples, frames=frames,
                  lock_before=project(raw['lock_before'], LOCK_FIELDS),
                  lock_after=project(raw['lock_after'], LOCK_FIELDS),
                  final_state=project(raw['final_state'], UI_FIELDS),
                  scope='Unconfigured admission remedy via production ui.key, no fixture unlock. '
                        'No PIN submission, SD enrollment, radio start or TX. '
                        'Not physical keypad/touch or unlocked-feature acceptance. '
                        'Raw USB/serial/backup evidence remains private. '
                        'Initial sandbox-denied attempt made no device changes and is retained locally.')
    check(result)
    return result


def check(data):
    require(data['schema'] == 'leshy.device_lock.entry_remedy.hil.v1' and data['status'] == 'passed', 'terminal/schema')
    require(data['source_commit'] == SOURCE and data['firmware_version'] == VERSION, 'source/version binding')
    require(data['app_sha256'] == APP and data['app_elf_sha256'] == ELF, 'candidate binding')
    require(data['metrics']['version'] == VERSION and data['metrics']['app_elf_sha256'] == ELF, 'live binding')
    for key in ('raw_evidence_sha256', 'runner_sha256'):
        require(re.fullmatch('[0-9a-f]{64}', data[key]) is not None, 'missing provenance hash')
    for state in (data['lock_before'], data['lock_after']):
        require(state['status'] == 'unconfigured' and state['credential_generation'] == 0, 'credentials changed')
        require(not any(state[k] for k in ('protected_access', 'worker_active', 'radio_touched', 'persistence_fixture_active')),
                'admission/worker/fixture side effect')
    require(data['lock_before'] == data['lock_after'], 'lock state changed')
    seen, nested = set(), set()
    last_home, last_device, pending = None, None, None
    editor_cancel = False
    lock_samples = 0
    input_samples = 0
    for sample in data['samples']:
        command, state = sample['command'], sample['value']
        if command == 'device-lock.state':
            require(state == data['lock_before'], 'intermediate lock mutation')
            lock_samples += 1
            continue
        if command == 'input.state':
            require(state['read_errors'] == state['queue_drops'] == 0, 'input errors/drops')
            input_samples += 1
            continue
        require(command == 'ui.state' or command in ('ui.key up', 'ui.key down', 'ui.key left', 'ui.key right', 'ui.key select'),
                'unsupported action')
        # Device owns UiForeground (bit 0) for its existing settings route;
        # the nested remedy retains that parent, but never acquires RF resources.
        expected_lease = 1 if state['runtime_owner'] == 'device' else 0
        require(state['lease_mask'] == expected_lease and state['runtime_owner'] in ('none', 'device'), 'unexpected lease')
        require(state['survey_product_store_bytes_written'] == 0 and not state['survey_product_store_open_attempted'], 'storage touched')
        if state['page'] == 'device_lock' and state['runtime_event'] == 'setup_required' and command in ('ui.key select', 'ui.key right'):
            if state['parent_page'] == 'home':
                require(last_home is not None and state['runtime_owner'] == 'none', 'Home origin')
                pending = ('home', last_home['selected_id'], last_home['selection'])
            else:
                require(state['parent_page'] == 'device' and last_device is not None, 'Device origin')
                pending = ('device', last_device['device_selection'])
        if state['runtime_event'] == 'device_lock_editor_cancelled':
            require(state['page'] == 'device_lock', 'editor cancel left remedy')
            editor_cancel = True
        if pending and command == 'ui.key left' and state['page'] == pending[0]:
            if pending[0] == 'home':
                require((state['selected_id'], state['selection']) == pending[1:], 'lost Home focus')
                seen.add(pending[1])
            else:
                require(state['device_selection'] == pending[1], 'lost Device focus')
                nested.add(pending[1])
            pending = None
        if state['page'] == 'home':
            last_home = state
        elif state['page'] == 'device':
            last_device = state
    require({'wifi', 'spectrum24', 'subghz'} <= seen and {1, 8} <= nested, 'missing roundtrip')
    require(lock_samples >= 5 and input_samples > 0 and pending is None, 'missing intermediate/final diagnostics')
    require(editor_cancel, 'missing editor cancel')
    a, b = (data['frames'][name] for name in ('setup-required', 'setup-required-stable'))
    require(a['state']['page'] == b['state']['page'] == 'device_lock', 'wrong captured page')
    require(a['pixel_sha256'] == b['pixel_sha256'], 'unstable pixels')
    editor = data['frames']['pin-editor-cancellable']
    require(editor['state']['runtime_event'] == 'device_lock_editor_opened' and
            editor['pixel_sha256'] != a['pixel_sha256'], 'editor not separately opened')
    for key in ('ui_full_repaints', 'ui_delta_repaints'):
        require(a['state'][key] == b['state'][key], 'steady-state repaint')
    final = data['final_state']
    require(final['page'] == 'home' and final['runtime_owner'] == 'none' and final['lease_mask'] == 0, 'final lease')
    # Historical source remains a checkable independent artifact, not current HEAD.
    source = subprocess.check_output(['git', 'show', SOURCE + ':firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp'], cwd=ROOT, text=True)
    require(source.count('leshy1::apps::device::showDeviceLockAdmission(') == 2, 'both entry paths must route remedy')


def mutation_tests(data):
    mutations = (
        lambda d: d.update(app_sha256='0' * 64),
        lambda d: d['metrics'].update(app_elf_sha256='0' * 64),
        lambda d: d['lock_after'].update(credential_generation=1),
        lambda d: d['lock_after'].update(protected_access=True),
        lambda d: d['lock_before'].update(worker_active=True),
        lambda d: d['frames']['setup-required-stable'].update(pixel_sha256='0' * 64),
        lambda d: d['frames']['setup-required-stable']['state'].update(ui_full_repaints=-1),
        lambda d: d['final_state'].update(lease_mask=1),
        lambda d: d.update(samples=[]),
    )
    for mutate in mutations:
        tampered = copy.deepcopy(data)
        mutate(tampered)
        try:
            check(tampered)
        except ValueError:
            continue
        raise ValueError('tampered evidence was accepted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retain', type=Path, help='private raw run.json to project')
    parser.add_argument('--evidence', type=Path, default=DEFAULT)
    args = parser.parse_args()
    if args.retain:
        require(not args.evidence.exists(), 'refuse to overwrite retained evidence')
        data = retain(args.retain)
        args.evidence.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    else:
        data = json.loads(args.evidence.read_text())
    check(data)
    mutation_tests(data)
    print('Device Lock entry HIL passed: three Home and two Device roundtrips, stable pixels, unchanged credentials; 9 tamper negatives passed')


if __name__ == '__main__':
    main()
