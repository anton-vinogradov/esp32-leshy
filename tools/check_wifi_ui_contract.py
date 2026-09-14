#!/usr/bin/env python3
"""Guard the hardware bridge of the host-tested Wi-Fi UI components."""
from check_live_render_contract import ENTRY, function_body

source = ENTRY.read_text()
detail = function_body(source, "void renderWifiNetworkDetailData()")
radar = function_body(source, "void renderWifiNetworkRadar(")
bar = function_body(source, "void renderWifiChannelBar(")
text = function_body(source, "bool renderWifiNetworkText(")
selection = function_body(source, "UiDeltaRenderResult renderSelectionDelta()")
for scene in ("wifiProductView", "bleProductView", "rfSpectrumView"):
    marker = f"renderedUi.{scene} != static_cast<std::uint8_t>({scene})"
    assert marker in selection
    assert selection.index(marker) < selection.index("uiController.isRoot()")
assert "display.fillRect" not in detail
assert "display.fillRect" not in radar
assert "renderRadioSignalCardDelta" in radar
assert "paintLayeredBarDelta" in bar
assert "clearHeight" not in bar
assert "wifiNetworkTextCache.changed" in text
assert "if (painted) wifiNetworkTextCache.publish" in text
assert "kWifiNetworkActionsBounds, point.x, point.y" in source
assert "wifiNetworkNavigation.rowCount()" in source
name_request = function_body(source, "bool requestWifiNameListen() {")
name_handoff = function_body(source, "void finishWifiNameSurveyHandoff(bool quiescent) {")
name_stop = function_body(source, "bool stopWifiNameListen(bool resume) {")
name_service = function_body(source, "void serviceWifiNameListen() {")
generic_capture = function_body(source, "void serviceWifiFrameCapture() {")
assert "if (wifiNameBusy()) return" in generic_capture # No generic lease release.
assert "requestProductSurveyWorkerStop(true)" in name_request
assert "!wifiNameRouteAllowed()" in name_request and "beginNameMonitor" not in name_request
assert name_handoff.index("if (!quiescent)") < name_handoff.index("beginNameMonitor")
assert name_handoff.index("wifiNameCancelPending || !wifiNameRouteAllowed()") < name_handoff.index("beginNameMonitor")
assert "wifiFrameCapture.stop(nowUs) && wifiFrameCapture.cleanupComplete()" in name_stop
assert "cleanup && resume && !wasFailed && resumeWifiNameSurvey()" in name_stop
assert "!wifiNameRouteAllowed()" in name_service and "stopWifiNameListen(false)" in name_service
adapter = (ENTRY.parent / "BoardWifiPassiveCapture.cpp").read_text()
name_begin = function_body(adapter, "bool BoardWifiPassiveCapture::beginNameMonitor(")
assert "plan.durationMs = 20000U" in name_begin and "plan.channel = channel" in name_begin
ingress = function_body(adapter, "void BoardWifiPassiveCapture::accept(")
name_ingress = ingress[ingress.index("if (nameMonitor_)"):ingress.index("if (authenticationCapture_)")]
assert "!receiveValid || type != WIFI_PKT_MGMT" in name_ingress
assert "frame.monotonicUs - stats.startedUs < 20000000ULL" in name_ingress
assert "decodeWifiNetworkName" in name_ingress and "capture_.append" not in name_ingress
print("Wi-Fi shared rendering/navigation bridge passed")
