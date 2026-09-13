#!/usr/bin/env python3
"""Integration guard for ADR-008; native tests exercise admission behavior."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp'


def block(text, marker):
    start = text.index('{', text.index(marker))
    depth = 0
    for end in range(start, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start + 1:end]
    raise ValueError('unclosed block: ' + marker)


def main():
    source = ENTRY.read_text()
    header = (ROOT / 'firmware/leshy1/src/apps/survey/ProductSurveyAdmission.h').read_text()
    assert 'bool persistent = true;' in block(header, 'struct ProductSurveyRequest')
    for name in ('startWifiNetworksProduct()', 'startBleDevicesProduct()'):
        assert 'surveyWorkflow.configure(false, false)' in block(source, 'bool ' + name)
    assert 'surveyWorkflow.configure(true, false)' in block(source, 'bool openWifiVisitProduct()')
    prepare = block(source, 'ProductSurveyWorkerReport prepareProductSurveyWorker(')
    durable = block(prepare, 'if (persistent)')
    for token in ('loadProductFingerprint(', 'BoardSdSpiTransport',
                  'runSdIdentificationStateMachine(', 'knownProductSessionRootExists(',
                  'authorizeProductStore('):
        assert prepare.count(token) == durable.count(token) == 1, token
    assert 'ProductStorePermit storePermit{};' in prepare
    assert 'storePermit.writable =' not in prepare and 'storePermit.status =' not in prepare
    assert 'unavailableRequest.persistent = persistent;' in prepare
    assert 'surveyRequest.persistent = persistent;' in prepare
    assert 'productSurveyRuntime.persistent = surveyWorkflow.persistent();' in block(source, 'bool startProductSurvey()')
    for name in ('reopenProductSurveyBackendForCommit()', 'commitPausedProductSurvey()'):
        assert block(source, 'bool ' + name).strip().startswith(
            ('// Defense in depth: no UI/worker path may save a live-only session.\n'
             '    if (!productSurveyRuntime.persistent) return false;') if name.startswith('reopen') else
            'if (!productSurveyRuntime.persistent) return false;')
    assert 'cancel = cancel || !productSurveyRuntime.persistent;' in block(source, 'bool requestProductSurveyWorkerStop(bool cancel)')
    ready = source[source.index('const bool liveSurveyReady ='):source.index('inventory.add({"survey.simulated"')]
    assert 'productSurveyWorkerReady && flashMatches && psramMatches' in ready
    assert 'liveSurveyReady ? CapabilityState::Available' in ready
    assert 'passive_ble_live_worker_ready_no_sd' in ready
    native = (ROOT / 'tests/native/clean_target_tests.cpp').read_text()
    assert 'void testExplicitLiveSurveyWithoutStorage()' in native
    assert 'testExplicitLiveSurveyWithoutStorage();' in native
    print('Live radio/SD contract passed: explicit RAM-only RX, no SD admission or commit; persistent visits remain fail-closed')


if __name__ == '__main__':
    main()
