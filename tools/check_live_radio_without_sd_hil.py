#!/usr/bin/env python3
"""Check scoped Wi-Fi acceptance while retaining the failed warm BLE transition.

Only allowlisted state/counts and frame hashes leave private work/outputs.
No SSID, BSSID, BLE address, USB identity or framebuffer is retained publicly.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

from check_device_lock_entry_hil import LOCK_FIELDS, project, require

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'tests/hil/evidence/board-03-live-radio-1.0.0-dev.381.json'
SOURCE = '4d395ec43a2f0df345311fbe51a5a03a00a22b50'
VERSION = '1.0.0-dev.381'
APP = 'cef80a6d80a00dffd4ab4a5f61138b8a052f523e891d8c057ffd11e3a11653bc'
ELF = '2f39fa772fc9536dad4340c979962bd8fea3147089aeda7202567fd61c58c54c'
ZERO = ('survey_product_identity_attempts', 'survey_product_filesystem_mount_attempts',
        'survey_product_mount_attempts_total', 'survey_product_store_bytes_written',
        'survey_scan_driver_error', 'survey_scan_dropped', 'survey_ble_scan_dropped',
        'survey_dropped', 'survey_timeline_overflow')
FALSE = ('survey_product_backend_open', 'survey_product_storage_mounted',
         'survey_product_store_open_attempted', 'survey_simulated')
BASE = ('page', 'runtime_owner', 'lease_mask', 'runtime_event',
        'survey_persistent', 'survey_product_admission_status',
        'survey_product_status', 'survey_product_source_active',
        'survey_product_cleanup_complete', 'survey_product_active_source_mask',
        'survey_running', 'wifi_product_view', 'ble_product_view') + ZERO + FALSE
NET = ('wifi_networks_unique', 'wifi_networks_strongest_first',
       'survey_product_wifi_scan_cycles')
BLE = ('ble_devices_unique', 'survey_product_ble_scan_cycles', 'ble_begin_error',
       'ble_begin_heap_free_before', 'ble_begin_heap_largest_before')
DEVICE = ('wifi_devices_unique', 'wifi_device_frames_reported',
          'wifi_device_clients_dropped', 'wifi_device_monitor_active',
          'wifi_device_nvs_disabled', 'wifi_device_volatile_storage_only')
CHANNEL = ('wifi_channel_frames_reported', 'wifi_channel_measured_mask',
           'wifi_channel_completed_sweeps', 'wifi_channel_monitor_active')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retain(failed_path, cold_path):
    failed, cold = (json.loads(p.read_text()) for p in (failed_path, cold_path))
    require(failed['status'] == 'failed' and 'ble_memory_unavailable' in failed['error'], 'lost warm failure')
    require(cold['status'] == 'passed' and cold['scope'] == 'wifi_live_without_sd_admission', 'cold scope failed')
    require(cold['prior_failed_sha256'] == digest(failed_path), 'failure provenance')
    for run in (failed, cold):
        require((run['source_commit'], run['firmware_version'], run['app_sha256'], run['app_elf_sha256']) ==
                (SOURCE, VERSION, APP, ELF), 'raw candidate')
    frames = {}
    for name, frame in failed['frames'].items():
        fields = NET if name.startswith(('network', 'networks')) else DEVICE if name == 'wifi-devices' else CHANNEL
        frames[name] = dict(pixel_sha256=frame['pixel_sha256'], state=project(frame['state'], BASE + fields))
    samples = failed['samples'] + cold['samples']
    states = [s['value'] for s in samples if s['value'].get('schema') == 'leshy.ui.v1']
    locks = [project(s['value'], LOCK_FIELDS) for s in samples if s['command'] == 'device-lock.state']
    failure = next(s for s in states if s['runtime_event'] == 'ble_memory_unavailable')
    # Inspect every captured state, including the failure and cleanup, not just happy-path frames.
    maxima = {k:max(s[k] for s in states) for k in ZERO}
    occurrences = {k:sum(bool(s[k]) for s in states) for k in FALSE}
    return dict(schema='leshy.live_radio.sd_independence.hil.v1', status='partial',
                wifi_status='passed', ble_status='failed_after_wifi', board_id='board-03',
                source_commit=SOURCE, firmware_version=VERSION, app_sha256=APP, app_elf_sha256=ELF,
                provenance=dict(warm_raw=digest(failed_path), cold_raw=digest(cold_path),
                                warm_runner=digest(ROOT / 'work/board03_live_radio.py'),
                                cold_runner=digest(ROOT / 'work/board03_live_radio_cold.py')),
                warm_run_status=failed['status'], cold_run_status=cold['status'],
                checks=dict(warm=failed['checks'], cold=cold['checks']),
                audit=dict(sample_count=len(states), zero_maxima=maxima, true_occurrences=occurrences,
                           simulated_idle_samples=sum(s['survey_simulated'] and not s['survey_running']
                               and not s['survey_product_source_active'] and not s['survey_product_source_start_attempted']
                               for s in states)),
                frames=frames, locks=locks,
                boots=[dict(ready_ms=b['ready_ms'], usb_open_attempts=b['attempts'],
                            disconnects=b['disconnects']) for b in failed['boots'] + cold['boots']],
                warm_ble_failure=project(failure, BASE + BLE),
                cold_ble=project(cold['ble_cold_diagnostic'], BASE + BLE),
                heap_endpoints=cold['heap_endpoints'],
                final_input=project(cold['final_input'], ('read_errors', 'queue_drops')),
                finals=[project(run['final_state'], BASE) for run in (failed, cold)],
                limits=['Wi-Fi live routes accepted; warm Wi-Fi-to-BLE transition remains failed, not full radio acceptance.',
                        'Card stayed inserted but unenrolled; no-card admission is host-tested, not a card-removal HIL claim.',
                        'All live samples have zero SD identity/mount/write attempts; boot read-only recovery is separate.',
                        'Device monitor received frames but observed no clients during this bounded run; no client-detail acceptance.',
                        'Persistent positive Save, decryption of original-board files and SD write integrity not tested.',
                        'No RF TX, GATT connection, PIN change, laptop Wi-Fi change or PSRAM qualification.',
                        'Production ui.key used; physical keys/touch and optical flicker are not accepted by this run.'])


def safe(s):
    require(all(s[k] == 0 for k in ZERO) and not any(s[k] for k in FALSE), 'SD/simulation/drop side effect')


def check(data):
    require((data['schema'], data['status'], data['wifi_status'], data['ble_status']) ==
            ('leshy.live_radio.sd_independence.hil.v1', 'partial', 'passed', 'failed_after_wifi'), 'scope cannot hide BLE failure')
    require((data['source_commit'], data['firmware_version'], data['app_sha256'], data['app_elf_sha256']) ==
            (SOURCE, VERSION, APP, ELF), 'candidate binding')
    require(data['warm_run_status'] == 'failed' and data['cold_run_status'] == 'passed', 'terminal evidence')
    require(set(data['provenance']) == {'warm_raw', 'cold_raw', 'warm_runner', 'cold_runner'} and
            all(re.fullmatch('[0-9a-f]{64}', v) for v in data['provenance'].values()), 'provenance')
    audit = data['audit']
    # Bootstrap workflow has a default simulated flag before any source is started.
    # It is not a live result; every such sample must be fully idle.
    require(audit['sample_count'] >= 100 and audit['zero_maxima'] == dict.fromkeys(ZERO, 0)
            and audit['true_occurrences'] == {**dict.fromkeys(FALSE, 0),
                'survey_simulated': audit['simulated_idle_samples']}, 'all-state safety audit')
    require(data['checks']['warm'] == dict.fromkeys(('app_only_boot_and_key_unchanged', 'wifi_channels_all_13',
            'wifi_devices_receive', 'wifi_networks_right', 'wifi_networks_select'), True), 'warm paths')
    require(data['checks']['cold'] == {'cold_and_repeated_wifi_key_and_heap': True}, 'cold path')
    expected_frames = {'networks-0', 'networks-1', 'network-detail-0', 'network-detail-1', 'wifi-devices', 'wifi-channels'}
    require(set(data['frames']) == expected_frames, 'missing UI frames')
    for name, frame in data['frames'].items():
        require(re.fullmatch('[0-9a-f]{64}', frame['pixel_sha256']), 'frame digest')
        s = frame['state']
        safe(s)
        require(s['runtime_owner'] == 'wifi' and s['lease_mask'] == 11, 'live lease must not include storage')
        if name.startswith(('network', 'networks')):
            require(not s['survey_persistent'] and s['survey_running'] and s['survey_product_admission_status'] == 'permitted'
                    and s['survey_product_active_source_mask'] == 1 and s['wifi_networks_unique'] > 0
                    and s['wifi_networks_strongest_first'] and s['survey_product_wifi_scan_cycles'] >= 2, 'live networks')
            require(s['wifi_product_view'] == ('network_detail' if name.startswith('network-detail') else 'networks'), 'detail/list route')
        elif name == 'wifi-devices':
            require(s['wifi_product_view'] == 'devices' and s['wifi_device_monitor_active']
                    and s['wifi_device_frames_reported'] > 0 and s['wifi_device_clients_dropped'] == 0
                    and s['wifi_device_nvs_disabled'] and s['wifi_device_volatile_storage_only'], 'passive device frames')
        else:
            require(s['wifi_product_view'] == 'channels' and s['wifi_channel_monitor_active'] and
                    s['wifi_channel_measured_mask'] == 8191 and s['wifi_channel_completed_sweeps'] >= 1
                    and s['wifi_channel_frames_reported'] > 0, 'all channels')
    failed, cold = data['warm_ble_failure'], data['cold_ble']
    for s in (failed, cold): safe(s)
    require(failed['runtime_event'] == failed['survey_product_status'] == 'ble_memory_unavailable'
            and not failed['survey_product_source_active'] and failed['ble_begin_error'] == 257
            and failed['ble_begin_heap_largest_before'] < 28000, 'missing warm BLE memory failure')
    require(cold['ble_product_view'] == 'devices' and not cold['survey_persistent'] and cold['survey_running']
            and cold['survey_product_admission_status'] == 'permitted' and cold['survey_product_active_source_mask'] == 2
            and cold['survey_product_ble_scan_cycles'] >= 1 and cold['ble_devices_unique'] > 0
            and cold['ble_begin_heap_largest_before'] >= 28000, 'cold BLE comparison')
    locks = data['locks']
    require(len(locks) >= 6 and all(s == locks[0] for s in locks), 'credential continuity')
    require(locks[0]['status'] == 'unconfigured' and locks[0]['credential_generation'] == 0
            and locks[0]['protected_access'] and locks[0]['failure'] == 'none', 'PIN admission')
    require(len(data['boots']) == 3 and all(1 <= b['usb_open_attempts'] <= 8 and b['disconnects'] == 0 and
            0 < b['ready_ms'] < 35000 for b in data['boots']), 'boot continuity')
    endpoints = data['heap_endpoints']
    require(len(endpoints) == 3 and endpoints[0] == endpoints[1] == endpoints[2]
            and endpoints[0]['heap_free'] > 0 and endpoints[0]['heap_total'] > endpoints[0]['heap_free'], 'repeated Wi-Fi heap')
    require(data['final_input'] == {'read_errors': 0, 'queue_drops': 0}, 'input faults')
    require(len(data['finals']) == 2, 'missing final states')
    for s in data['finals']:
        safe(s)
        require(s['page'] == 'home' and s['runtime_owner'] == 'none' and s['lease_mask'] == 0
                and not s['survey_product_source_active'] and s['survey_product_cleanup_complete'], 'final cleanup')


def mutation_tests(data):
    changes = [lambda d:d.update(status='passed'), lambda d:d.update(ble_status='passed'),
               lambda d:d.update(app_sha256='0' * 64), lambda d:d.update(warm_run_status='passed'),
               lambda d:d['audit']['zero_maxima'].update(survey_product_store_bytes_written=1),
               lambda d:d['warm_ble_failure'].update(survey_product_source_active=True),
               lambda d:d['cold_ble'].update(survey_product_ble_scan_cycles=0),
               lambda d:d['heap_endpoints'][-1].update(heap_free=1),
               lambda d:d['locks'][-1].update(credential_generation=1),
               lambda d:d['finals'][-1].update(lease_mask=11), lambda d:d['boots'].pop(),
               lambda d:d['frames'].pop('network-detail-0'),
               lambda d:d['frames']['wifi-channels']['state'].update(wifi_channel_measured_mask=2047),
               lambda d:d['frames']['networks-0']['state'].update(survey_persistent=True),
               lambda d:d['frames']['wifi-devices']['state'].update(wifi_device_frames_reported=0)]
    for change in changes:
        bad = copy.deepcopy(data)
        change(bad)
        try: check(bad)
        except ValueError: continue
        raise ValueError('tampered evidence accepted')
    return len(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--failed', type=Path)
    parser.add_argument('--cold', type=Path)
    parser.add_argument('--evidence', type=Path, default=DEFAULT)
    args = parser.parse_args()
    data = retain(args.failed, args.cold) if args.failed and args.cold else json.loads(args.evidence.read_text())
    check(data)
    count = mutation_tests(data)
    if args.failed:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f'Wi-Fi no-SD-admission evidence valid; warm BLE failure retained; {count} tamper negatives passed')


if __name__ == '__main__':
    main()
