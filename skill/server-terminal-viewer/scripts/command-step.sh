# Define once in an authorized interactive Bash or Zsh shell. No remote files needed.
# Quote the complete command as one argument. Passwords belong in hidden prompts.
deck_step() {
    if [ "$#" -ne 1 ]; then
        printf '%s\n' 'Usage: deck_step '\''command'\''' >&2
        return 2
    fi
    printf '\n[执行命令] %s\n[状态] 执行中\n\n' "$1"
    local deck_exit_code=0
    bash -c "$1" || deck_exit_code=$?
    printf '\n[执行结束] 退出码 %s\n' "$deck_exit_code"
    return "$deck_exit_code"
}
