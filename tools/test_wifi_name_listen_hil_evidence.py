#!/usr/bin/env python3
"""Positive and tamper coverage without private board artifacts."""
import copy
import unittest
from test_wifi_product_network_hil_evidence import EvidenceTests, digest
from check_wifi_name_listen_hil import check, summary, NAME_STATES, NAME_SCREENS
from run_wifi_product_network_hil import bssid_hash, name_countdown_diff

class NameEvidenceTests(EvidenceTests):
    def setUp(self):
        super().setUp()
        r = self.run
        r.update(name_listener_requested=True,
                 name_listener_scope='passive_ap_frames_timeout_touch_stop_restore_no_client_association')
        r['states']['name_source'] = r['states']['started'].copy()
        base = dict(identity_hash=bssid_hash('020000000001'),ui_page='listen_name',
            active=True,passive=True,active_probe_allowed=False,channel=6,rssi_dbm=-70,ssid_known=False,
            name_listen_state='result',name_receiver_owned=False,name_scan_restored=True,
            name_window_found=False,name_window_source=0,name_window_conflict=False,
            name_ap_confirmed=True,name_window_duration_ms=20001,signal_samples=10,
            name_remaining_seconds=18)
        for label in NAME_STATES: r['states'][label] = base.copy()
        r['states']['name_ready'].update(name_listen_state='idle', name_window_duration_ms=0,
                                        name_scan_restored=False)
        for label in ('name_running','name_positive_start','name_ap_frame'):
            r['states'][label].update(name_listen_state='running',name_receiver_owned=True)
        for label in ('name_ap_frame','name_touch_stop'):
            r['states'][label].update(ssid_known=True,name_window_found=True,name_window_source=1,name_window_duration_ms=2500)
        r['states']['name_scan_resumed']['signal_samples']=11
        r['states']['name_after_stop_scan']['signal_samples']=12
        raw=bytes(153600); later=bytearray(raw); later[(161*240+3)*2]=1
        record=next(iter(r['screens'].values()))
        for label in NAME_SCREENS:
            frame=bytes(later) if label=='name-running-later' else raw
            (self.folder/'frames'/f'{label}.rgb565').write_bytes(frame)
            (self.folder/'frames'/f'{label}.png').write_bytes(b'fixture-png')
            r['screens'][label]=copy.deepcopy(record)
            r['screens'][label].update(rgb565_sha256=digest(frame),png_sha256=digest(b'fixture-png'))
        r['name_countdown_pixels']=name_countdown_diff(raw,later)

    def test_positive(self): self.assertEqual(check(self.run,self.folder), [])
    def test_name_tamper(self):
        for label,key,value in (
            ('name_ready','name_receiver_owned',True),
            ('name_ready','name_window_duration_ms',20000),
            ('name_ready','name_window_found',True),
            ('name_ready','name_scan_restored',True),
            ('name_running','name_remaining_seconds',21),
            ('name_deadline','name_window_duration_ms',1000),
            ('name_deadline','name_window_found',True),
            ('name_ap_frame','name_window_source',2),
            ('name_ap_frame','signal_samples',99),
            ('name_ap_frame','rssi_dbm',-20),
            ('name_touch_stop','name_receiver_owned',True),
            ('name_touch_stop','name_window_duration_ms',20000),
            ('name_after_stop_scan','signal_samples',10)):
            r=copy.deepcopy(self.run);r['states'][label][key]=value
            with self.subTest(label=label,key=key): self.assertTrue(check(r,self.folder))
    def test_missing_requested_delta(self):
        self.run['name_listener_requested']=False
        self.assertTrue(check(self.run,self.folder))
    def test_name_static_pixel_tamper(self):
        p=self.folder/'frames/name-running-later.rgb565'
        frame=bytearray(p.read_bytes());frame[0]=1;p.write_bytes(frame)
        self.run['screens']['name-running-later']['rgb565_sha256']=digest(frame)
        self.run['name_countdown_pixels']=name_countdown_diff(bytes(153600),frame)
        self.assertTrue(check(self.run,self.folder))
    def test_name_summary_limits(self):
        result=summary(self.run,b'run',[])
        self.assertIn('no real client positive yet',result['limits'])
        self.assertNotIn('identity_hash',str(result['name_listener']))

if __name__ == '__main__': unittest.main()
