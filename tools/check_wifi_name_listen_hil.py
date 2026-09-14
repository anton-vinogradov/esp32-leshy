#!/usr/bin/env python3
"""Validate the ordinary two-DIV name-listener delta, without exporting identities."""
import argparse
import hashlib
import json
from pathlib import Path
from check_wifi_product_network_hil import check as check_product, summary as product_summary
from run_wifi_product_network_hil import bssid_hash, name_countdown_diff

NAME_SCREENS = ('name-ready', 'name-running', 'name-running-later', 'name-timeout', 'name-found')
NAME_STATES = ('name_ready', 'name_running', 'name_deadline', 'name_scan_resumed',
               'name_positive_start', 'name_ap_frame', 'name_touch_stop', 'name_after_stop_scan')

def check(run, folder):
    failures = check_product(run, folder)
    def need(ok, text):
        if not ok: failures.append(text)
    need(run.get('name_listener_requested') is True, 'name delta requested')
    need(run.get('name_listener_scope') == 'passive_ap_frames_timeout_touch_stop_restore_no_client_association', 'scope')
    states = run.get('states', {})
    name_source = states.get('name_source', {})
    mac = name_source.get('bssid', '')
    try: identity = bssid_hash(mac)
    except (ValueError, TypeError): identity = None; mac = ''
    need(len(mac) == 12 and name_source.get('active') is True and name_source.get('hidden') is True and
         name_source.get('ssid') == 'LESHY-TEST-' + mac[-4:].upper(), 'fresh session-bound own AP')
    for label in NAME_STATES:
        s = states.get(label, {})
        need(s.get('identity_hash') == identity and s.get('ui_page') == 'listen_name' and
             s.get('active') is True and s.get('passive') is True and
             s.get('active_probe_allowed') is False and s.get('channel') == 6, label + ' target/passive/page')
    ready = states.get('name_ready', {})
    need(ready.get('name_listen_state') == 'idle' and ready.get('name_receiver_owned') is False and
         ready.get('ssid_known') is False and ready.get('name_window_duration_ms') == 0 and
         ready.get('name_window_found') is False and ready.get('name_scan_restored') is False,
         'no start on entry / hidden target / no stale result')
    for label in ('name_running', 'name_positive_start', 'name_ap_frame'):
        s = states.get(label, {})
        need(s.get('name_listen_state') == 'running' and s.get('name_receiver_owned') is True and
             0 < s.get('name_remaining_seconds', 0) <= 20, label + ' running bounds')
    end = states.get('name_deadline', {})
    need(end.get('name_window_found') is False and end.get('name_window_source') == 0 and
         20000 <= end.get('name_window_duration_ms', 0) <= 21000, 'honest hidden timeout')
    positive, beginning = states.get('name_ap_frame', {}), states.get('name_positive_start', {})
    need(positive.get('ssid_known') is True and positive.get('name_window_found') is True and positive.get('name_window_source') == 1 and
         positive.get('name_ap_confirmed') is True and positive.get('name_window_conflict') is False, 'live AP frame provenance')
    need(positive.get('signal_samples') == beginning.get('signal_samples') and
         positive.get('rssi_dbm') == beginning.get('rssi_dbm'), 'name does not replace AP signal')
    stop = states.get('name_touch_stop', {})
    need(0 < stop.get('name_window_duration_ms', 0) < 20000 and stop.get('name_window_found') is True, 'manual stop before deadline')
    for label in ('name_deadline', 'name_scan_resumed', 'name_touch_stop', 'name_after_stop_scan'):
        s = states.get(label, {})
        need(s.get('name_listen_state') == 'result' and s.get('name_scan_restored') is True and
             s.get('name_receiver_owned') is False, label + ' cleanup/restore')
    need(states.get('name_scan_resumed', {}).get('signal_samples', 0) >
         states.get('name_running', {}).get('signal_samples', 0), 'fresh scan after deadline')
    need(states.get('name_after_stop_scan', {}).get('signal_samples', 0) >
         positive.get('signal_samples', 0), 'fresh scan after manual stop')
    for label in NAME_SCREENS:
        record = run.get('screens', {}).get(label, {})
        for ext, key in (('png', 'png_sha256'), ('rgb565', 'rgb565_sha256')):
            path = folder / 'frames' / (label + '.' + ext)
            need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record.get(key), label + ' ' + ext)
            if ext == 'rgb565': need(path.is_file() and path.stat().st_size == 153600, label + ' complete TFT')
        begin, end = record.get('frame_begin', {}), record.get('frame_end', {})
        need(begin.get('width') == 240 and begin.get('height') == 320 and begin.get('format') == 'rgb565be' and
             begin.get('bytes') == end.get('bytes') == 153600 and
             begin.get('revision') == end.get('revision') == record.get('state', {}).get('revision'), label + ' continuity')
    try:
        pixels = name_countdown_diff((folder/'frames/name-running.rgb565').read_bytes(),
                                     (folder/'frames/name-running-later.rgb565').read_bytes())
        need(pixels == run.get('name_countdown_pixels') and pixels['static_pixels'] == 0 and
             pixels['dynamic_pixels'] > 0, 'name retained countdown pixels')
    except (OSError, RuntimeError): need(False, 'name complete countdown')
    return failures

def summary(run, raw, failures):
    result = product_summary(run, raw, failures)
    result['schema'] = 'leshy.wifi_name_listen.acceptance.v1'
    fields = ('name_listen_state', 'name_window_source', 'name_window_found',
              'name_window_duration_ms', 'name_scan_restored', 'name_receiver_owned', 'signal_samples')
    result['name_listener'] = {label: {k: run['states'][label].get(k) for k in fields} for label in NAME_STATES}
    result['name_countdown_pixels'] = run['name_countdown_pixels']
    result['name_history_retention'] = run.get('name_history_retention', {})
    result['history_before_cleanup'] = {role: {key: run['cleanup'][role].get('initial_state', {}).get(key)
        for key in ('survey_received', 'survey_forwarded', 'survey_dropped', 'survey_scan_dropped')}
        for role in ('source', 'receiver')}
    result['screens'].update({label: {k: run['screens'][label][k] for k in ('png_sha256','rgb565_sha256')} for label in NAME_SCREENS})
    result['limits'] = ('Live AP-frame name listener, hidden timeout, manual stop and scan restore verified. '
        'Client association/reassociation and conflict handling have host coverage only; no real client positive yet. '
        'Live catalogs are separate from the bounded 64-record survey history; its capacity drops are reported, '
        'not interpreted as zero-loss capture. Final zero counters are cleanup state only. '
        'No optical flicker, BOOT/lock fault injection, heap invariance, endurance or broad-matrix acceptance.')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args()
    raw = args.run.read_bytes(); run = json.loads(raw)
    failures = check(run, args.run.parent)
    if failures:
        print(json.dumps({'status':'failed','failures':failures})); raise SystemExit(1)
    if args.summary:
        with args.summary.open('x') as output: output.write(json.dumps(summary(run, raw, failures),indent=2)+'\n')
    print('ordinary two-DIV name listener delta verified; client-association positive remains open')
