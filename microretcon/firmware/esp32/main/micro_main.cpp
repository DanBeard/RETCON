// MicroRETCON board plan — config consumption + mode/profile pick.
// SCAFFOLD: the FAT mount + crns parse wiring lands with M2's real main;
// the shared-channel rule and profile mapping below are the design,
// written where they will live so M2 implements rather than invents.
#include "micro_main.hpp"

namespace micro::main {

BoardPlan load_board_plan(const char* config_path) {
    BoardPlan plan{};

    // M2: mount FAT, then crns::host::load_config(config_dir, plan.rns,
    // warn_fn). The [micro] section arrives in plan.rns.micro (crns M1).
    //
    // Shared-channel rule (DESIGN §3): if [[wifi]] brings an AP up, the
    // AP's channel wins and ESP-NOW follows. Computed at bring-up once
    // the WiFi result is known; here the config value stands as the
    // standalone default:
    plan.espnow_channel = plan.rns.micro.espnow_channel;

    // Profile pick (crns M1 pinned decision 5): the MAPPING lives here.
    // Defaults to Node; Router is opt-in once measured (DESIGN §9:
    // footprint_budget_bytes at build time — regression = red build).
    // transport + router is a supported combo, not the default.
    plan.profile = BoardPlan::Profile::Node;

    return plan;
}

}  // namespace micro::main