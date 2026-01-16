#!/usr/bin/env bash
#
# RETCON Shell Utilities
# Shared functions for consistent CLI output across scripts
#

# Prevent double-sourcing
if [ -n "$SHELL_UTILS_LOADED" ]; then
    return 0 2>/dev/null || exit 0
fi
SHELL_UTILS_LOADED=1

# =============================================================================
# Color Definitions
# =============================================================================

# Detect terminal color support
if [ -t 1 ] && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    COLORS_ENABLED=1
else
    COLORS_ENABLED=0
fi

if [ "$COLORS_ENABLED" -eq 1 ]; then
    readonly COLOR_RESET='\033[0m'
    readonly COLOR_RED='\033[0;31m'
    readonly COLOR_GREEN='\033[0;32m'
    readonly COLOR_YELLOW='\033[1;33m'
    readonly COLOR_BLUE='\033[0;34m'
    readonly COLOR_CYAN='\033[0;36m'
    readonly COLOR_BOLD='\033[1m'
    readonly COLOR_DIM='\033[2m'
else
    readonly COLOR_RESET=''
    readonly COLOR_RED=''
    readonly COLOR_GREEN=''
    readonly COLOR_YELLOW=''
    readonly COLOR_BLUE=''
    readonly COLOR_CYAN=''
    readonly COLOR_BOLD=''
    readonly COLOR_DIM=''
fi

# =============================================================================
# Logging Functions
# =============================================================================

# log_info <message>
# Prints an informational message in cyan
log_info() {
    echo -e "${COLOR_CYAN}[INFO]${COLOR_RESET} $1"
}

# log_success <message>
# Prints a success message in green
log_success() {
    echo -e "${COLOR_GREEN}[OK]${COLOR_RESET} $1"
}

# log_warn <message>
# Prints a warning message in yellow
log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $1"
}

# log_error <message>
# Prints an error message in red
log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $1"
}

# log_step <step_num> <total_steps> <message>
# Prints a step counter with blue highlighting
log_step() {
    local step=$1
    local total=$2
    local message=$3
    echo -e "${COLOR_BLUE}[${step}/${total}]${COLOR_RESET} ${message}"
}

# =============================================================================
# Visual Formatting Functions
# =============================================================================

# print_header <title>
# Prints a prominent section header with box drawing
print_header() {
    local title="$1"
    local width=50
    local line=""
    for ((i=0; i<width; i++)); do line+="═"; done
    echo ""
    echo -e "${COLOR_BOLD}${line}${COLOR_RESET}"
    echo -e "${COLOR_BOLD}  ${title}${COLOR_RESET}"
    echo -e "${COLOR_BOLD}${line}${COLOR_RESET}"
    echo ""
}

# print_section <title>
# Prints a smaller section divider
print_section() {
    local title="$1"
    local width=50
    local title_len=${#title}
    local dash_len=$((width - title_len - 4))
    local dashes=""
    for ((i=0; i<dash_len; i++)); do dashes+="─"; done
    echo ""
    echo -e "${COLOR_DIM}── ${COLOR_RESET}${COLOR_BOLD}${title}${COLOR_RESET}${COLOR_DIM} ${dashes}${COLOR_RESET}"
    echo ""
}

# print_summary <title> <items...>
# Prints a completion summary box
print_summary() {
    local title="$1"
    shift
    local items=("$@")
    local width=50
    local inner=$((width - 2))

    # Build horizontal lines
    local hline=""
    for ((i=0; i<inner; i++)); do hline+="─"; done

    echo ""
    echo "┌${hline}┐"
    printf "│  %-$((inner - 2))s│\n" "$title"
    echo "├${hline}┤"
    for item in "${items[@]}"; do
        printf "│  ${COLOR_GREEN}[OK]${COLOR_RESET} %-$((inner - 7))s│\n" "$item"
    done
    echo "└${hline}┘"
    echo ""
}

# print_failure_summary <title> <items...>
# Prints a failure summary box in red
print_failure_summary() {
    local title="$1"
    shift
    local items=("$@")
    local width=50
    local inner=$((width - 2))

    local hline=""
    for ((i=0; i<inner; i++)); do hline+="─"; done

    echo ""
    echo -e "${COLOR_RED}┌${hline}┐${COLOR_RESET}"
    printf "${COLOR_RED}│${COLOR_RESET}  %-$((inner - 2))s${COLOR_RED}│${COLOR_RESET}\n" "$title"
    echo -e "${COLOR_RED}├${hline}┤${COLOR_RESET}"
    for item in "${items[@]}"; do
        printf "${COLOR_RED}│${COLOR_RESET}  ${COLOR_RED}[FAIL]${COLOR_RESET} %-$((inner - 9))s${COLOR_RED}│${COLOR_RESET}\n" "$item"
    done
    echo -e "${COLOR_RED}└${hline}┘${COLOR_RESET}"
    echo ""
}

# =============================================================================
# User Interaction Functions
# =============================================================================

# prompt_confirm <message>
# Prompts user for y/n confirmation with colored feedback
# Returns 0 for yes, 1 for no
prompt_confirm() {
    while true; do
        read -r -n 1 -p "${1:-Continue?} [y/n]: " REPLY
        case $REPLY in
            [yY]) echo ; return 0 ;;
            [nN]) echo ; return 1 ;;
            *) printf " ${COLOR_RED}invalid input${COLOR_RESET}\n"
        esac
    done
}

# prompt_menu <allow_default> <option1> [option2] ...
# Displays a numbered menu and prompts for selection
# Sets MENU_SELECTION to selected index (1-based), or 0 if default chosen
# Arguments:
#   allow_default: "true" to allow Enter for default (index 0), "false" to require selection
#   options: list of menu options to display
# Returns 0 on valid selection
MENU_SELECTION=0
prompt_menu() {
    local allow_default="$1"
    shift
    local options=("$@")
    local count=${#options[@]}

    # Display options
    echo ""
    for ((i=0; i<count; i++)); do
        printf "  ${COLOR_CYAN}[%d]${COLOR_RESET} %s\n" "$((i+1))" "${options[$i]}"
    done
    echo ""

    # Build prompt
    local prompt_text
    if [ "$allow_default" = "true" ]; then
        prompt_text="Select [1-${count}] or press Enter to keep current: "
    else
        prompt_text="Select [1-${count}]: "
    fi

    # Get selection
    while true; do
        read -r -p "$prompt_text" REPLY

        # Handle Enter (empty input)
        if [ -z "$REPLY" ]; then
            if [ "$allow_default" = "true" ]; then
                MENU_SELECTION=0
                return 0
            else
                printf "${COLOR_RED}Selection required${COLOR_RESET}\n"
                continue
            fi
        fi

        # Validate numeric input
        if ! [[ "$REPLY" =~ ^[0-9]+$ ]]; then
            printf "${COLOR_RED}Invalid input - enter a number${COLOR_RESET}\n"
            continue
        fi

        # Validate range
        if [ "$REPLY" -lt 1 ] || [ "$REPLY" -gt "$count" ]; then
            printf "${COLOR_RED}Invalid selection - choose 1-${count}${COLOR_RESET}\n"
            continue
        fi

        MENU_SELECTION=$REPLY
        return 0
    done
}

# =============================================================================
# Progress Indication Functions
# =============================================================================

SPINNER_PID=""

# spinner_start <message>
# Starts a background spinner with message
spinner_start() {
    local message="$1"
    local spin_chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'

    # Don't use spinner if not a terminal
    if [ ! -t 1 ]; then
        echo "$message..."
        return
    fi

    (
        while true; do
            for ((i=0; i<${#spin_chars}; i++)); do
                printf "\r${COLOR_CYAN}%s${COLOR_RESET} %s " "${spin_chars:$i:1}" "$message"
                sleep 0.1
            done
        done
    ) &
    SPINNER_PID=$!
    disown $SPINNER_PID 2>/dev/null
}

# spinner_stop
# Stops the background spinner and clears the line
spinner_stop() {
    if [ -n "$SPINNER_PID" ]; then
        kill "$SPINNER_PID" 2>/dev/null
        wait "$SPINNER_PID" 2>/dev/null
        printf "\r\033[K"  # Clear the line
        SPINNER_PID=""
    fi
}

# run_with_spinner <message> <command...>
# Runs a command with a spinner, showing success/failure
run_with_spinner() {
    local message="$1"
    shift

    spinner_start "$message"
    if "$@" > /dev/null 2>&1; then
        spinner_stop
        log_success "$message"
        return 0
    else
        spinner_stop
        log_error "$message - FAILED"
        return 1
    fi
}

# run_verbose <message> <command...>
# Runs a command showing output, with clear start/end markers
run_verbose() {
    local message="$1"
    shift

    log_info "Starting: $message"
    local sep=""
    for ((i=0; i<40; i++)); do sep+="─"; done
    echo -e "${COLOR_DIM}${sep}${COLOR_RESET}"
    if "$@"; then
        echo -e "${COLOR_DIM}${sep}${COLOR_RESET}"
        log_success "$message"
        return 0
    else
        echo -e "${COLOR_DIM}${sep}${COLOR_RESET}"
        log_error "$message - FAILED"
        return 1
    fi
}

# =============================================================================
# Error Handling Functions
# =============================================================================

# check_root
# Exits with error if not running as root
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_error "This script must be run as root (try: sudo $0)"
        exit 1
    fi
}

# check_command <command_name>
# Returns 0 if command exists, 1 otherwise
check_command() {
    command -v "$1" &> /dev/null
}

# check_dependencies <cmd1> <cmd2> ...
# Checks for required commands, exits with error listing missing ones
check_dependencies() {
    local missing=()
    for cmd in "$@"; do
        if ! check_command "$cmd"; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing required commands: ${missing[*]}"
        exit 1
    fi
    log_success "All dependencies satisfied"
}

# apt_install <package1> <package2> ...
# Wrapper for apt install with proper error handling
apt_install() {
    local packages=("$@")

    if sudo apt install -y "${packages[@]}"; then
        return 0
    else
        log_error "Failed to install packages: ${packages[*]}"
        log_info "Try: sudo apt update && sudo apt --fix-broken install"
        return 1
    fi
}

# cleanup_spinner
# Trap handler to ensure spinner is stopped on exit
cleanup_spinner() {
    spinner_stop
}

# Setup trap to clean up spinner on script exit
trap cleanup_spinner EXIT
