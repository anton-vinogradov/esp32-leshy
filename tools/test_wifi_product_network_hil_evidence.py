#!/usr/bin/env python3
"""Private-artifact-free positive/tamper tests for ordinary two-DIV evidence."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from check_wifi_product_network_hil import check, summary, SCREENS, FINAL
from run_wifi_product_network_hil import bssid_hash, countdown_diff

def digest(data): return hashlib.sha256(data).hexdigest()

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / 'frames').mkdir()
        image = bytearray(288); image[0] = 0xe9
        struct.pack_into('<I', image, 32, 0xabcd5432)
        image[176:208] = bytes.fromhex('01' * 32)
        (self.folder / 'firmware.bin').write_bytes(image)
        boot = {'app_elf_sha256': '01' * 32, 'version': 'fixture',
                'heap_total': 10, 'heap_free': 5, 'heap_min_free': 4}
        self.run = r = dict(schema='leshy.wifi_product_network.run.v1', status='pass',
            failures=[], board_identities={'source': 'a'*64, 'receiver': 'b'*64},
            app_elf_sha256=boot['app_elf_sha256'], image_sha256=digest(image),
            deadline_observed_s=60.1, screens={}, cleanup={}, states={})
        for role in ('source', 'receiver'):
            r[role+'_boot'] = boot.copy(); r[role+'_final_boot'] = boot.copy()
            r['cleanup'][role] = {'complete': True, 'final_state': FINAL.copy()}
        mac = '020000000001'
        base = dict(active=False, radio_started=False, cleanup_complete=True,
                    lease_mask=1, limit_ms=60000, channel=6, bssid=mac,
                    ssid='LESHY-TEST-0001', hidden=True, power_quarter_dbm=8, error=0)
        for name in ('menu_off','started','visible_source','user_stop','deadline_start','deadline'):
            r['states'][name] = base.copy()
        for name in ('started','visible_source','deadline_start'):
            r['states'][name].update(active=True,radio_started=True,lease_mask=3,cleanup_complete=False)
        r['states']['started']['remaining_s'] = 60
        r['states']['visible_source'].update(hidden=False,remaining_s=50)
        r['states']['user_stop']['stop_reason'] = 1
        r['states']['deadline']['stop_reason'] = 2
        for i,name in enumerate(('hidden','hidden_no_name','resolved','retained')):
            r['states'][name] = dict(identity_hash=bssid_hash(mac),active=True,passive=True,
                active_probe_allowed=False,ssid_known=i>=2,channel=6,authentication='WPA2-PSK',
                signal_samples=i+1,hidden_resolutions=int(i>=2),list_content_clears=0,
                list_slot_clears=0,live_list_direct_fallbacks=0,live_list_row_allocation_failures=0)
        raw = bytes(153600); later = bytearray(raw); later[(241*240+3)*2] = 1
        for name in SCREENS:
            frame = bytes(later) if name == 'source-running-later' else raw
            (self.folder/'frames'/f'{name}.rgb565').write_bytes(frame)
            (self.folder/'frames'/f'{name}.png').write_bytes(b'fixture-png')
            r['screens'][name] = dict(rgb565_sha256=digest(frame),png_sha256=digest(b'fixture-png'),
                frame_begin=dict(width=240,height=320,format='rgb565be',bytes=153600,revision=1),
                frame_end=dict(bytes=153600,revision=1),state=dict(revision=1,
                    self_test_view='wifi_network',self_test_read_only=False,self_test_status='not_run'))
        r['countdown_pixels'] = countdown_diff(raw,later)

    def test_positive(self): self.assertEqual(check(self.run,self.folder), [])
    def test_same_board(self):
        self.run['board_identities']['receiver'] = 'a'*64
        self.assertIn('two distinct physical identities',check(self.run,self.folder))
    def test_wrong_image(self):
        self.run['receiver_final_boot']['app_elf_sha256'] = '02'*32
        self.assertTrue(check(self.run,self.folder))
    def test_not_same_ap(self):
        self.run['states']['resolved']['identity_hash'] += 1
        self.assertTrue(check(self.run,self.folder))
    def test_stale_or_missing_name(self):
        for name,value in (('signal_samples',1),('ssid_known',False)):
            changed=copy.deepcopy(self.run); changed['states']['resolved'][name]=value
            self.assertTrue(check(changed,self.folder))
    def test_deadline_not_measured(self):
        self.run['deadline_observed_s'] = 2
        self.assertTrue(check(self.run,self.folder))
    def test_radio_not_stopped(self):
        self.run['states']['deadline']['radio_started'] = True
        self.assertTrue(check(self.run,self.folder))
    def test_drops_or_sd(self):
        for key in ('survey_dropped','survey_product_store_bytes_written'):
            changed=copy.deepcopy(self.run); changed['cleanup']['receiver']['final_state'][key]=1
            self.assertTrue(check(changed,self.folder))
    def test_readonly_mislabel(self):
        self.run['screens']['source-running']['state']['self_test_read_only'] = True
        self.assertTrue(check(self.run,self.folder))
    def test_static_pixels_changed(self):
        path=self.folder/'frames/source-running-later.rgb565'
        frame=bytearray(path.read_bytes()); frame[0]=1; path.write_bytes(frame)
        self.run['screens']['source-running-later']['rgb565_sha256']=digest(frame)
        self.run['countdown_pixels']=countdown_diff(bytes(153600),frame)
        self.assertTrue(check(self.run,self.folder))
    def test_truncated_frame(self):
        path=self.folder/'frames/hidden.rgb565'; path.write_bytes(b'short')
        self.run['screens']['hidden']['rgb565_sha256']=digest(b'short')
        self.assertTrue(check(self.run,self.folder))
    def test_private_fields_not_exported(self):
        self.run['ambient_secret']='private-example'
        result=json.dumps(summary(self.run,b'run',[]))
        for private in ('private-example','020000000001','LESHY-TEST-0001','board_identities'):
            self.assertNotIn(private,result)

if __name__ == '__main__': unittest.main()
