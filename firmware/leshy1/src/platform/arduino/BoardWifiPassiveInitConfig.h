#pragma once

#include <esp_wifi.h>

namespace leshy1::platform::arduino {

struct BoardWifiPassiveInitProfile final {
    static constexpr int kStaticRxBuffers = 4;
    static constexpr int kDynamicRxBuffers = 8;
    static constexpr int kStaticTxBuffers = 0;
    static constexpr int kDynamicTxBuffers = 4;
    static constexpr int kManagementShortBuffers = 6;
};

inline wifi_init_config_t makeBoardWifiPassiveOnlyInitConfig() {
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    // Passive survey/capture never associates or carries application data.
    // Keep one bounded no-PSRAM profile for every ESP Wi-Fi RX-only adapter.
    init.static_rx_buf_num = BoardWifiPassiveInitProfile::kStaticRxBuffers;
    init.dynamic_rx_buf_num = BoardWifiPassiveInitProfile::kDynamicRxBuffers;
    init.tx_buf_type = 1;
    init.static_tx_buf_num = BoardWifiPassiveInitProfile::kStaticTxBuffers;
    init.dynamic_tx_buf_num = BoardWifiPassiveInitProfile::kDynamicTxBuffers;
    init.ampdu_rx_enable = 0;
    init.ampdu_tx_enable = 0;
    init.amsdu_tx_enable = 0;
    init.rx_ba_win = 0;
    init.mgmt_sbuf_num =
        BoardWifiPassiveInitProfile::kManagementShortBuffers;
    init.nvs_enable = 0;
    return init;
}

}  // namespace leshy1::platform::arduino
