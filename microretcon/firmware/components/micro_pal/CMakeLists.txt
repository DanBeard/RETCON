# micro_pal: ESP32 PAL for crns — ESP-NOW + SX1262 interfaces.
# ESP-IDF only auto-discovers immediate children of components/, so each
# subcomponent has its own CMakeLists (registered from the top level via
# EXTRA_COMPONENT_DIRS in the future if we mirror rWatch's out-of-tree
# pattern; for now they are direct children).
