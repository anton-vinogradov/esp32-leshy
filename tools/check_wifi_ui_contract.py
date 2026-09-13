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
print("Wi-Fi shared rendering/navigation bridge passed")
