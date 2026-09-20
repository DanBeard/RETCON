idf_component_register(
    SRCS "main.cpp" "micro_main.cpp"
    INCLUDE_DIRS "."
    REQUIRES micro_pal micro_usb
)
