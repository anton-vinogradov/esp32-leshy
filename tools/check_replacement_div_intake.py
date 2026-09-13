#!/usr/bin/env python3
"""Offline check of board-03's partial intake; never qualify absent physical tests."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'tests/hil/evidence/board-03-intake-20260913'
def read(name): return json.loads((BUNDLE/name).read_text())
def require(condition, message):
    if not condition: raise ValueError(message)

def check():
    for line in (BUNDLE/'artifacts.sha256').read_text().splitlines():
        digest,name=line.split('  ',1)
        p=(BUNDLE/name).resolve()
        require(p.is_relative_to(BUNDLE.resolve()),'artifact escapes bundle')
        require(hashlib.sha256(p.read_bytes()).hexdigest()==digest,'hash: '+name)
    summary=read('summary.json')
    require(summary['status']=='partial_receiver_intake_passed','not partial')
    require(summary['full_functional_acceptance'] is False,'overstated acceptance')
    require(summary['scope']['fixture_tx_admitted'] is False,'fixture not qualified')
    require(summary['backup']['published'] is False,'factory image must stay local')
    backup=read('backup-manifest.json')
    require(backup['mac']==summary['base_mac'] and backup['board']==summary['board_id'],'backup board')
    require(backup['bytes']==summary['backup']['bytes']==16777216,'backup length')
    require(backup['sha256']==summary['backup']['sha256'],'backup digest')
    require(backup['verification']=='esptool verify_flash: digest matched','backup verification')
    require(summary['positive_facts']['psram_enabled_or_tested'] is False,'PSRAM not tested')
    rom=read('rom-profile.json')
    require(rom['chip']['base_mac']==summary['base_mac'],'wrong board')
    require(all(op['returncode']==0 and op['read_only'] for op in rom['operations']), 'ROM command failed')
    require(rom['accepted_for_fixture_flash'] is False,'assembly unconfirmed')
    probe=read('shield-receivers.json')
    require(probe['status']=='pass' and probe['detected_receivers']==3,'receiver identities')
    require(all(n['detected'] and n['status']==14 for n in probe['nrf']),'nRF identity')
    require(probe['cc1101']['version']==20,'CC1101 identity')
    require(all(v==0 for v in probe['side_effects'].values()),'probe side effects')
    require(probe['cleanup_complete'],'probe cleanup')
    rf=read('active-rf.json')
    require(rf['step']=='complete' and rf['cleanup_complete'] and rf['resource_released'],'RF terminal')
    require(rf['rx_only'] and all(v==0 for v in rf['side_effects'].values()),'RF side effects')
    for name in ('nrf24','cc1101','subghz_ook','subghz_fsk','infrared'):
        require(rf[name]['complete'] and rf[name]['passed'] and rf[name]['cleanup_complete'],name)
    require(rf['nrf24']['modules']==3 and rf['nrf24']['channels']==83,'all three nRF')
    require(rf['cc1101']['bins']==64,'CC sweep incomplete')
    require(rf['infrared']['transitions']==0,'update optical IR scope before acceptance')
    wifi=read('wifi-ingress.json')
    require(wifi['status']=='valid' and wifi['records_read']>0 and wifi['observations_dropped']==0,'Wi-Fi reception')
    require(wifi['explicit_passive_only'] and wifi['cleanup_complete'] and not wifi['storage_written'],'Wi-Fi cleanup/scope')
    ble=read('ble-isolated.json')
    manifest=read('ble-probe-manifest.json')
    retained_sources={
        'work/board03-ble-probe/platformio.ini': 'source/ble-platformio.ini',
        'work/board03-ble-probe/src/adapter.cpp': 'source/ble-adapter.cpp',
        'work/board03-ble-probe/src/main.cpp': 'source/ble-main.cpp',
    }
    for path,expected in manifest['inputs'].items():
        if path in retained_sources:
            content=(BUNDLE/retained_sources[path]).read_bytes()
        else:
            require(path.startswith('firmware/leshy1/src/'),'unexpected BLE source')
            content=subprocess.run(
                ['git','show',summary['source_commit']+':'+path],
                cwd=ROOT,check=True,stdout=subprocess.PIPE,
            ).stdout
        require(hashlib.sha256(content).hexdigest()==expected,'BLE input hash: '+path)
    require(ble['app_elf_sha256']==manifest['app_elf_sha256'] and ble['mac']==summary['base_mac'],'BLE identity')
    require(ble['status']=='valid' and ble['accepted']>0 and ble['dropped']==0,'BLE reception')
    require(ble['cleanup_complete'] and ble['passive_only'] and ble['application_tx_calls']==0 and ble['storage_calls']==0,'BLE scope')
    sd=read('sd-identify.json')
    require(sd['wire_status']=='response_timeout' and not sd['write_commands'] and sd['cleanup_complete'],'SD unresolved/scope')
    require(read('active-artifact.json')['step']=='failed','do not claim full plan pass')
    for name in ('spectrum24','subghz'):
        require(read(name+'-start.json')['runtime_event']=='setup_required','screen blocked reason')
        require(read(name+'-live.json')['sweeps']==0,'screen not a positive RF result')
    metrics=read('restored-product-metrics.json')
    require(metrics['app_elf_sha256']==summary['product_app_elf_sha256'] and metrics['version']==summary['product_version'],'product restore identity')
    state=read('restored-home-frame.json')['state']
    require(state['page']=='home' and state['runtime_owner']=='none' and state['lease_mask']==0,'final lease')
    require(all(read('final-safe-outputs.json')[k] for k in ('buzzer_inactive','nrf_ce_inactive','software_quiesce_complete')),'final pads')
    require(read('final-safety.json')['armed'] and not read('final-safety.json')['latched'],'final safety')
    require(read('final-lock.json')['status']=='unconfigured','product PIN changed')
    for key in ('read_errors','queue_drops','press_events'):
        require(read('final-input.json')[key]==0,'physical input not clean/unreviewed')
    print('board-03 intake checked: Wi-Fi/BLE receive + 3 nRF/CC RX smoke; partial, SD/manual/known-signal gates remain open')

if __name__=='__main__': check()
