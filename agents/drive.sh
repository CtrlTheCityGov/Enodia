#!/bin/zsh
# drive.sh <task> [steps…]: tests -> code -> review for one task, each step a separate agent in .worktrees/<task>.
#   <task> is A<n> (Dev A track: map & HUD) or B<n> (Dev B track: data & backend).
#   Steps default to: tests code review.  Prompts come from agents/gen-prompts.sh.
#
# Three runners (RUNNER env var):
#   RUNNER=agy    (default if `agy` and `hc` exist) Antigravity in background `hc` sessions:
#                 tests Gemini Hydrogen, code $CODE_MODEL (default Gemini Neon), review Gemini Argon.
#   RUNNER=codex  Codex in background `hc` sessions (when `hc` exists) or `codex exec`:
#                 uses $CODEX_MODEL if set, else Codex's configured default model.
#   RUNNER=claude (default otherwise) Claude Code CLI in the foreground, one step after the other:
#                 tests $TESTS_MODEL (sonnet), code $CODE_MODEL (opus), review $REVIEW_MODEL (sonnet).
# Mixed: CLAUDE_STEPS="code" or CODEX_STEPS="code" (space-separated) sends just those steps to Claude or Codex
#   and the rest to Antigravity, e.g. CODEX_STEPS=code agents/drive.sh B10 -> tests Gemini, code Codex, review Gemini.
# The rule that matters: the test writer and the reviewer are never the same agent/model as the implementer.
n=$1; shift; steps=("$@"); (( $#steps )) || steps=(tests code review); t=${(L)n}
[[ $n == [AB]<-> ]] || { echo "usage: drive.sh A<n>|B<n> [tests code review]"; exit 64; }
M=$(git rev-parse --show-toplevel); W=$M/.worktrees
[[ -d $W/$n ]] || { echo "no worktree $W/$n: see CLAUDE.md 'Start a task'"; exit 66; }
if [[ -z $RUNNER ]]; then (( $+commands[agy] && $+commands[hc] )) && RUNNER=agy || RUNNER=claude; fi

for step in $steps; do
  prompt="Read $W/$n-$step-prompt.md and do exactly what it says."
  [[ -f $W/$n-$step-prompt.md ]] || { echo "missing $W/$n-$step-prompt.md (run agents/gen-prompts.sh)"; exit 66; }
  runner=$RUNNER
  [[ " $CLAUDE_STEPS " == *" $step "* ]] && runner=claude
  [[ " $CODEX_STEPS " == *" $step "* ]] && runner=codex
  if [[ $runner == claude ]]; then
    case $step in
      code)   model=${CODE_MODEL:-opus} ;;
      review) model=${REVIEW_MODEL:-sonnet} ;;
      *)      model=${TESTS_MODEL:-sonnet} ;;
    esac
    echo "$n $step: claude --model $model (foreground)"
    (cd $W/$n && claude -p "$prompt" --model $model --permission-mode auto --add-dir $W $M) || { echo "$n $step: failed"; exit 1; }
  elif [[ $runner == codex ]]; then
    mflag=(); [[ -n $CODEX_MODEL ]] && mflag=(-m $CODEX_MODEL)
    if (( $+commands[hc] )); then
      hc kill $t-$step >/dev/null 2>&1; hc rm $t-$step >/dev/null 2>&1
      hc run --bg --outlive-parent --name $t-$step --cwd $W/$n codex --dangerously-bypass-approvals-and-sandbox --add-dir $W --add-dir $M $mflag "$prompt" >/dev/null
      sleep 15
      while :; do s=$(hc get $t-$step --json | python3 -c "import json,sys;d=json.load(sys.stdin);st=d.get('status') or {};print(d['state'], st.get('state') if isinstance(st,dict) else st)")
        case "$s" in *error*) echo "$n $step: $s; chain stopped, resume with hc send $t-$step"; exit 1;; *done*|*idle*|finished*) break;; esac; sleep 15; done
      echo "$n $step (codex): $s"
    else
      echo "$n $step: codex exec (foreground)"
      (cd $W/$n && codex exec --dangerously-bypass-approvals-and-sandbox --add-dir $W --add-dir $M $mflag "$prompt") || { echo "$n $step: failed"; exit 1; }
    fi
  else
    case $step in
      code)   model=${CODE_MODEL:-gemini-4-neon-high} ;;
      review) model=gemini-4-argon-high ;;
      *)      model=gemini-4-hydrogen-high ;;
    esac
    hc kill $t-$step >/dev/null 2>&1; hc rm $t-$step >/dev/null 2>&1
    hc run --bg --outlive-parent --name $t-$step --cwd $W/$n agy --model $model --dangerously-skip-permissions -i "$prompt" >/dev/null
    for i in 1 2 3 4; do sleep 10; hc read $t-$step 2>/dev/null | grep -qiE "trust this folder|trust the files|trust the contents" && { hc keys $t-$step enter >/dev/null; break; }; done
    sleep 30
    while :; do s=$(hc get $t-$step --json | python3 -c "import json,sys;d=json.load(sys.stdin);st=d.get('status') or {};print(d['state'], st.get('state') if isinstance(st,dict) else st)")
      case "$s" in *error*) echo "$n $step: $s; chain stopped, resume with hc send $t-$step"; exit 1;; *done*|*idle*|finished*) break;; esac; sleep 20; done
    echo "$n $step: $s"
  fi
  # An implementer that stopped with questions made no "<task>:" commit; never review that.
  if [[ $step == code ]] && ! git -C $W/$n log -1 --format=%s | grep -q "^$n:"; then
    echo "$n code: no '$n:' commit (questions? read $W/$n-code-report.md); chain stopped"; exit 2; fi
done
