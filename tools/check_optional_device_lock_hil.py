#!/usr/bin/env python3
"""Retain a non-identifying PIN-only delta; never convert the Wi-Fi failure to pass."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

from check_device_lock_entry_hil import LOCK_FIELDS, PUBLIC_SOURCE_BASE, UI_FIELDS, project, require

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'tests/hil/evidence/board-03-optional-pin-1.0.0-dev.380.json'
SOURCE = '343119bbd29dc78615a10b32e888c46141a96fce'
VERSION = '1.0.0-dev.380'
APP = 'a0f9483bb31341dd73505b9df09f0f6cfbb8ad312d6bff6c286bca1b76bd2158'
ELF = '2a41a35a6dc0c29d354667e048b5ee8cdb89c243dc91c2d0ebed302b5ba230e1'
PROTECTED = ('protected_ui', 'protected_evidence', 'secret_read', 'export',
             'backup', 'companion', 'sensitive_settings')
SAFE = ('status', 'lock', 'safe_stop', 'panic', 'cleanup', 'update_recovery', 'factory_reset')
UI = UI_FIELDS + ('wifi_product_view', 'survey_product_source_start_attempted',
                  'survey_source_selected_mask')
RADIO = ('adapter_active', 'cleanup_complete', 'current_owner', 'current_lease_mask',
         'rx_only', 'sweeps', 'side_effects', 'state', 'status', 'profile_declared',
         'waterfall_measurements_skipped')
INPUT = ('read_errors', 'queue_drops', 'press_events')


def retain(path):
    raw = json.loads(path.read_text())
    require(raw['status'] == 'passed', 'PIN/menu delta is not terminal')
    samples = []
    for item in raw['samples']:
        command, value = item['command'], item['value']
        if command == 'metrics':
            fields = ('version', 'app_elf_sha256')
        elif command == 'device-lock.state':
            fields = LOCK_FIELDS
        elif command == 'device-lock.admission':
            fields = ('state', 'access', 'protected_content_returned', 'radio_touched')
        elif command == 'input.state':
            fields = INPUT
        elif command == 'hardware.nrf24.spectrum':
            fields = RADIO + ('modules', 'active_slot_mask', 'channels')
        elif command == 'hardware.cc1101.spectrum':
            fields = RADIO + ('partnum', 'version', 'bins')
        else:
            require(command in ('ui.state', 'ui.key up', 'ui.key down', 'ui.key left',
                                'ui.key right', 'ui.key select'), 'unexpected command')
            fields = UI
        samples.append(dict(command=command, value=project(value, fields)))
    prior_path = ROOT / raw['prior_failed_run']
    prior = json.loads(prior_path.read_text())
    require(prior['status'] == 'failed' and 'No live networks before deadline' in prior['error'],
            'must retain the earlier genuine Wi-Fi failure')
    failed_state = next(s['value'] for s in prior['samples']
                        if s['command'] == 'ui.key right' and s['value']['runtime_event'] == 'source_plan_empty')
    blocker_fields = ('runtime_event', 'wifi_product_view', 'survey_source_selected_mask',
                      'survey_product_source_start_attempted')
    data = dict(schema='leshy.device_lock.optional_pin.hil.v1', status='passed',
                scope='optional_pin_and_radio_menu_entry', board_id='board-03',
                source_commit=raw['source_commit'], firmware_version=raw['firmware_version'],
                app_sha256=raw['app_sha256'], app_elf_sha256=raw['app_elf_sha256'],
                raw_evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                runner_sha256=hashlib.sha256((ROOT / 'work/board03_optional_pin_resume.py').read_bytes()).hexdigest(),
                samples=samples, boots=raw['boots'],
                frames={name: dict(pixel_sha256=f['pixel_sha256'], png_sha256=f['png_sha256'],
                                   state=project(f['state'], UI)) for name, f in raw['frames'].items()},
                final_state=project(raw['final_state'], UI),
                prior_wifi_failure=dict(status=prior['status'],
                    raw_sha256=hashlib.sha256(prior_path.read_bytes()).hexdigest(),
                    observed=project(failed_state, blocker_fields)),
                wifi_blocker=project(raw['wifi_blocker'], blocker_fields),
                limits=['Wi-Fi Nearby Networks reception remains blocked on unenrolled media; not accepted.',
                        'No PIN enrollment/disable/reset, SD enrollment or RF TX in this run.',
                        'Configured PIN/retry/recovery/fault semantics are host-tested, not re-enrolled on this board.',
                        'Production ui.key on physical hardware, not physical keypad/touch acceptance.',
                        'No PSRAM, optical IR, antenna calibration, TX or full-board qualification.',
                        'One earlier reset attempt failed before ROM connection; retained privately, then corrected to default_reset.'])
    check(data)
    return data


def check(data):
    require((data['schema'], data['status'], data['scope']) ==
            ('leshy.device_lock.optional_pin.hil.v1', 'passed', 'optional_pin_and_radio_menu_entry'), 'scope/terminal')
    require((data['source_commit'], data['firmware_version'], data['app_sha256'], data['app_elf_sha256']) ==
            (SOURCE, VERSION, APP, ELF), 'candidate binding')
    for digest in (data['raw_evidence_sha256'], data['runner_sha256'], data['prior_wifi_failure']['raw_sha256']):
        require(re.fullmatch('[0-9a-f]{64}', digest) is not None, 'provenance hash')
    expected_block = dict(runtime_event='source_plan_empty', wifi_product_view='menu',
                          survey_source_selected_mask=0, survey_product_source_start_attempted=False)
    require(data['prior_wifi_failure']['status'] == 'failed' and
            data['prior_wifi_failure']['observed'] == data['wifi_blocker'] == expected_block, 'hidden Wi-Fi failure')
    require(len(data['boots']) == 2 and all(0 < b['ready_ms'] < 35000 and b['attempts'] == 1
            and b['disconnects'] == 0 for b in data['boots']), 'reset/ready evidence')
    locks, metrics, matrices, inputs = [], [], [], []
    radio_states = {'hardware.nrf24.spectrum': [], 'hardware.cc1101.spectrum': []}
    entered, events = set(), set()
    for sample in data['samples']:
        command, s = sample['command'], sample['value']
        if command == 'device-lock.state':
            require(s['status'] == 'unconfigured' and s['credential_generation'] == 0 and
                    s['protected_access'] is True and s['failure'] == 'none' and s['failed_attempts'] == 0,
                    'PIN state changed/denied')
            require(not any(s[k] for k in ('worker_active', 'radio_touched', 'persistence_fixture_active')), 'fixture/worker')
            locks.append(s)
        elif command == 'metrics':
            require(s == dict(version=VERSION, app_elf_sha256=ELF), 'live identity')
            metrics.append(s)
        elif command == 'device-lock.admission':
            require(s['state'] == 'unconfigured' and not s['protected_content_returned'] and not s['radio_touched'], 'matrix side effects')
            require(all(s['access'][op] == 'allowed' for op in PROTECTED + SAFE + ('configure',)), 'operation admission')
            require(s['access']['unlock'] == s['access']['disable'] == 'setup_required', 'no phantom PIN session')
            matrices.append(s)
        elif command == 'input.state':
            require(s['read_errors'] == s['queue_drops'] == s['press_events'] == 0, 'input errors or physical-input claim')
            inputs.append(s)
        elif command in radio_states:
            expected = {'cc_command_strobes', 'storage_writes', 'tx_mode_entries', 'tx_payload_commands'} if command == 'hardware.nrf24.spectrum' else {'fifo_writes', 'pa_table_writes', 'rejected_strobes', 'storage_writes', 'tx_strobes'}
            require(set(s['side_effects']) == expected and all(v == 0 for v in s['side_effects'].values()), 'radio side effects')
            radio_states[command].append(s)
        else:
            require(command in ('ui.state', 'ui.key up', 'ui.key down', 'ui.key left', 'ui.key right', 'ui.key select'), 'unsupported action')
            require(s['runtime_owner'] in ('none', 'device', 'wifi', 'spectrum24', 'subghz'), 'unexpected owner')
            require(s['survey_product_store_bytes_written'] == 0 and not s['survey_product_store_open_attempted'], 'storage mutation')
            if command in ('ui.key right', 'ui.key select') and s['page'] == 'survey':
                entered.add(s['runtime_owner'])
            events.add(s['runtime_event'])
    require(len(locks) >= 5 and all(s == locks[0] for s in locks) and len(metrics) == 2 and len(matrices) == len(inputs) == 1,
            'missing state/boot coverage')
    require({'wifi', 'spectrum24', 'subghz'} <= entered and
            {'device_lock_editor_opened', 'device_lock_editor_cancelled'} <= events, 'missing UI paths')
    for command, states in radio_states.items():
        live = [s for s in states if s['adapter_active']]
        require(live and states[-1]['adapter_active'] is False and states[-1]['cleanup_complete'], 'radio cleanup')
        require(any(s['sweeps'] > 0 for s in live), 'no completed RX sweep')
        require(all(s['rx_only'] and s['state'] == 'running' and s['status'] == 'ready'
                    and s['current_lease_mask'] == 9 and s['waterfall_measurements_skipped'] == 0 for s in live), 'RX state')
        if command == 'hardware.nrf24.spectrum':
            require(all((s['modules'], s['active_slot_mask'], s['channels']) == (3, 7, 83) for s in live), 'three nRF receivers')
        else:
            require(all((s['partnum'], s['version'], s['bins']) == (0, 20, 64) for s in live), 'CC1101 receiver')
    a, b = (data['frames'][name] for name in ('pin-optional', 'pin-optional-stable'))
    require(a['state']['page'] == b['state']['page'] == 'device_lock' and a['pixel_sha256'] == b['pixel_sha256'], 'idle pixels')
    require(all(a['state'][k] == b['state'][k] for k in ('ui_full_repaints', 'ui_delta_repaints')), 'idle repaint')
    final = data['final_state']
    require(final['page'] == 'home' and final['runtime_owner'] == 'none' and final['lease_mask'] == 0
            and final['survey_product_store_bytes_written'] == 0, 'final lease/store')
    # The identical source blob is reachable from the public snapshot; the
    # original source commit also carries private intake and stays local.
    source = subprocess.check_output(['git', 'show', PUBLIC_SOURCE_BASE + ':firmware/leshy1/src/services/security/DeviceLock.cpp'], cwd=ROOT)
    require(hashlib.sha256(source).hexdigest() ==
            '11e6f1b2d8ad3f4c69d95a5036ec3d458730cec943e7bf669d985f3f02b8abe6',
            'historical DeviceLock source hash')
    source = source.decode('utf-8')
    require('dataKeyAvailable_ ? DeviceLockAccess::Allowed' in source, 'initialized key required')


def mutation_tests(data):
    mutations = [lambda d: d.update(app_sha256='0' * 64),
                 lambda d: d.update(scope='all_wifi_passed'),
                 lambda d: d['prior_wifi_failure'].update(status='passed'),
                 lambda d: d['wifi_blocker'].update(runtime_event='ready'),
                 lambda d: d.update(samples=[]),
                 lambda d: d['boots'].pop(),
                 lambda d: d['frames']['pin-optional-stable'].update(pixel_sha256='0' * 64),
                 lambda d: d['final_state'].update(lease_mask=9)]
    for command, field, bad in (('device-lock.state', 'protected_access', False),
                                ('device-lock.state', 'credential_generation', 1),
                                ('input.state', 'queue_drops', 1),
                                ('hardware.nrf24.spectrum', 'modules', 2),
                                ('hardware.cc1101.spectrum', 'rx_only', False)):
        mutations.append(lambda d, c=command, f=field, v=bad: next(s['value'] for s in d['samples'] if s['command'] == c).update({f: v}))
    for mutate in mutations:
        changed = copy.deepcopy(data)
        mutate(changed)
        try:
            check(changed)
        except ValueError:
            continue
        raise ValueError('tampered evidence accepted')
    return len(mutations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retain', type=Path)
    parser.add_argument('--evidence', type=Path, default=DEFAULT)
    args = parser.parse_args()
    if args.retain:
        require(not args.evidence.exists(), 'refuse retained evidence overwrite')
        data = retain(args.retain)
        mutation_tests(data)
        args.evidence.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    else:
        data = json.loads(args.evidence.read_text())
    check(data)
    print('Optional PIN delta passed; Wi-Fi storage blocker retained; %d tamper negatives passed' % mutation_tests(data))


if __name__ == '__main__':
    main()
