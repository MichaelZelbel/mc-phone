#!/usr/bin/env bash
# =============================================================================
# hub-phone: let your hub make a phone call for you.
#
# An add-on for the server from Chapter 32 of "Teach It Once". Logged in as root
# on that server, paste this one line:
#
#   curl -fsSL https://raw.githubusercontent.com/MichaelZelbel/hub-phone/main/install.sh | bash
#
# It is safe to run twice: a second run updates the code and the agent's prompt
# and keeps your settings. Nothing here deletes anything, and nothing here dials
# a number unless you say yes to the rehearsal at the very end.
#
# What it does on its own:
#   - puts the worker and the command on the machine (/opt/hub-phone,
#     /usr/local/bin/hub-phone) and the worker on the machine's own clock as a
#     system service that starts with the machine
#   - opens one socket for orders that only members of the hub-phone group may
#     use, and puts your assistant's account in that group; the account stays
#     sandboxed and never escalates
#   - creates the "Hub phone" agent in your ElevenLabs workspace from the prompt
#     this version ships, or brings an existing one up to date
#   - picks the phone number you imported into ElevenLabs
#   - copies the phone-errands recipe into your hub's skills room
#   - proves the assistant's account can reach the service, the way the
#     assistant will, not the way root can
#
# What it asks you: the ElevenLabs API key (once; hidden while you type), the
# name the assistant calls on behalf of, your own mobile number, your timezone,
# and, if more than one number is imported, which one to use. At the end it
# offers one rehearsal call to your own number (default: no).
#
# What only you can do first: setup/1-elevenlabs.md to 3-import-number.md, in
# the browser. Without an imported number the install finishes but says so.
# =============================================================================

# Not `set -e`: the shared primitives report a failure and return, and a
# half-installed add-on that says WHICH half beats one that quit on the first snag.
set -uo pipefail

KB_TAG="phone"
export KB_TAG

# The pin is an immutable TAG of the shared installer floor, never a branch.
KB_PIN="v2.7"
LIB_URL="https://raw.githubusercontent.com/MichaelZelbel/kit-bootstrap/$KB_PIN/lib.sh"
HP_TARBALL="${HP_TARBALL:-https://github.com/MichaelZelbel/hub-phone/archive/refs/heads/main.tar.gz}"
HP_SRC="${HP_SRC:-}"          # a local checkout, for tests and for running from a clone
AI_USER="${AI_USER:-ai}"
HUB="${HUB:-}"                # settled below: the assistant's home + /hub unless told otherwise
CONF=/etc/hub-phone/config.env
CRED=/etc/hub-phone/credentials.env

# --- The shared groundwork ----------------------------------------------------
if ! LIB="$(curl -fsSL "$LIB_URL")" || [ -z "$LIB" ]; then
  echo "Could not download the installer's shared parts from:" >&2
  echo "  $LIB_URL" >&2
  echo "Check the machine has internet, then run this again." >&2
  exit 1
fi
eval "$LIB"
unset LIB

kb_is_root || die "Run this as root on your server (the machine from Chapter 32)."
command -v systemctl >/dev/null 2>&1 || die "This needs systemd, which every Ubuntu server has. This machine does not."
need_tools python3 curl tar

# --- Hidden input for the key ------------------------------------------------
# lib.sh's ask() echoes what you type. A key must not be echoed or land in a log.
ask_secret() {   # $1 prompt -> stdout
  local answer=""
  have_tty || { printf ''; return 0; }
  kb_tell "$(printf "\033[1;34m[%s]\033[0m %s: " "$KB_TAG" "$1")"
  kb_resolve_tty
  case "$KB_TTY" in
    inherited) IFS= read -rs answer || true; printf '\n' >&2 ;;
    device)    IFS= read -rs answer < /dev/tty || true; printf '\n' > /dev/tty ;;
  esac
  printf '%s' "$answer"
}

# Values are written in double quotes, which systemd's EnvironmentFile strips, so a name
# with a space in it survives both systemd and a shell that sources the file.
conf_get() { [ -f "$CONF" ] && sed -n "s/^HUB_PHONE_$1=//p" "$CONF" | tail -1 | sed -e 's/^"//' -e 's/"$//'; }
conf_set() {   # $1 NAME  $2 value
  mkdir -p /etc/hub-phone; chmod 700 /etc/hub-phone
  touch "$CONF"
  sed -i "/^HUB_PHONE_$1=/d" "$CONF"
  printf 'HUB_PHONE_%s="%s"\n' "$1" "$2" >> "$CONF"
  chmod 600 "$CONF"
}

# --- 1. The code ---------------------------------------------------------------
say "The code"
WORK="$(mktemp -d)"
if [ -n "$HP_SRC" ] && [ -f "$HP_SRC/service/service.py" ]; then
  SRC="$HP_SRC"
  ok "using the checkout at $SRC"
else
  if ! curl -fsSL "$HP_TARBALL" | tar -xz -C "$WORK"; then
    die "Could not download hub-phone from $HP_TARBALL. Check the machine has internet, then run this again."
  fi
  SRC="$(find "$WORK" -maxdepth 1 -mindepth 1 -type d | head -1)"
  [ -f "$SRC/service/service.py" ] || die "The download did not contain hub-phone. Nothing was installed."
fi
install -d -m 755 /opt/hub-phone
install -d -m 700 /var/lib/hub-phone
for f in service.py call.py client.py setup.py prompt.txt; do
  install -m 644 "$SRC/service/$f" "/opt/hub-phone/$f"
done
cat > /usr/local/bin/hub-phone <<'SH'
#!/bin/sh
exec /usr/bin/python3 -I /opt/hub-phone/client.py "$@"
SH
chmod 755 /usr/local/bin/hub-phone
ok "code in /opt/hub-phone, command at /usr/local/bin/hub-phone"

# --- 2. Your settings ----------------------------------------------------------
say "Your settings"
mkdir -p /etc/hub-phone; chmod 700 /etc/hub-phone
if [ -s "$CRED" ] && grep -q '^ELEVENLABS_API_KEY=.' "$CRED"; then
  ok "the ElevenLabs key is already on this machine (kept; delete $CRED to enter a new one)"
else
  cat <<HOW
   The key comes from setup/1-elevenlabs.md: a restricted key with permission
   to write agents and a credit cap. It is stored in $CRED, readable by root
   only, and it is never printed.
HOW
  KEY="$(ask_secret "ElevenLabs API key")"
  [ -n "$KEY" ] || die "No key given. Make one as setup/1-elevenlabs.md shows, then run this again."
  case "$KEY" in *[[:space:]]*) die "The key contained a space or line break; paste it again." ;; esac
  printf 'ELEVENLABS_API_KEY=%s\n' "$KEY" > "$CRED"
  chmod 600 "$CRED"
  unset KEY
  ok "key stored"
fi

NAME="$(ask "Whose assistant is this? The name it gives on the phone (\"the AI assistant of ...\")" "$(conf_get CALLER_NAME)")"
[ -n "$NAME" ] || die "The assistant needs a name to call on behalf of."
conf_set CALLER_NAME "$NAME"

while :; do
  OWN="$(ask "Your own mobile number, international form (+49..., +1..., +44...)" "$(conf_get OWN_NUMBER)")"
  case "$OWN" in
    +[1-9][0-9][0-9][0-9][0-9][0-9][0-9]*) break ;;
    *) warn "That is not an international number. It starts with + and the country code, digits only." ;;
  esac
done
conf_set OWN_NUMBER "$OWN"

TZ_DEFAULT="$(conf_get TIMEZONE)"
[ -n "$TZ_DEFAULT" ] || TZ_DEFAULT="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
[ -n "$TZ_DEFAULT" ] || TZ_DEFAULT="UTC"
TZONE="$(ask "Your timezone, for 'Friday' and 'tomorrow' in an order" "$TZ_DEFAULT")"
if ! python3 -c "import sys, zoneinfo; zoneinfo.ZoneInfo(sys.argv[1])" "$TZONE" 2>/dev/null; then
  warn "'$TZONE' is not a timezone name Python knows (like Europe/Berlin). Using UTC; edit $CONF to change it."
  TZONE="UTC"
fi
conf_set TIMEZONE "$TZONE"
[ -n "$(conf_get DAILY_LIMIT)" ] || conf_set DAILY_LIMIT 5
[ -n "$(conf_get MAX_SECONDS)" ] || conf_set MAX_SECONDS 180
ok "settings in $CONF"

# --- 3. The service -------------------------------------------------------------
say "The service"
getent group hub-phone >/dev/null || groupadd --system hub-phone
JOINED=no
if id "$AI_USER" >/dev/null 2>&1; then
  if ! id -nG "$AI_USER" | tr ' ' '\n' | grep -qx hub-phone; then
    usermod -aG hub-phone "$AI_USER"
    JOINED=yes
  fi
  ok "account $AI_USER may place orders (member of hub-phone)"
else
  warn "there is no account called $AI_USER on this machine. The service is installed, but no
     account may place an order yet. Add one with: usermod -aG hub-phone <account>"
fi
for unit in hub-phone.service hub-phone-rpc.socket hub-phone-rpc@.service; do
  install -m 644 "$SRC/service/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now hub-phone-rpc.socket >/dev/null 2>&1 || die "The socket unit did not start: systemctl status hub-phone-rpc.socket"
systemctl enable hub-phone.service >/dev/null 2>&1
systemctl restart hub-phone.service || die "The worker did not start: journalctl -u hub-phone -n 20"
ok "worker running as a system service; socket open at /run/hub-phone-rpc.sock"

# A process carries the groups it had when it STARTED. If the assistant's gateway
# was already running, it cannot open the socket until it restarts.
if [ "$JOINED" = yes ]; then
  for gw in hermes-gateway hermes-gateway-hub; do
    if systemctl is-active --quiet "$gw.service" 2>/dev/null; then
      systemctl restart "$gw.service" && ok "$AI_USER joined hub-phone; restarted $gw so it carries the new group"
    fi
  done
fi

# --- 4. The agent and the number ---------------------------------------------
say "The agent in your ElevenLabs workspace"
AGENT_OUT="$(hub-phone setup agent --write 2>&1)"
if printf '%s' "$AGENT_OUT" | grep -q '"agent_id"'; then
  AGENT_ID="$(printf '%s' "$AGENT_OUT" | sed -n 's/.*"agent_id": *"\([^"]*\)".*/\1/p' | head -1)"
  STATUS="$(printf '%s' "$AGENT_OUT" | sed -n 's/.*"status": *"\([^"]*\)".*/\1/p' | head -1)"
  ok "agent \"Hub phone\" $STATUS ($AGENT_ID). Pick its voice in the ElevenLabs page if you like; everything else is set."
else
  warn "could not create or update the agent. ElevenLabs said:
     $AGENT_OUT
     The key may lack the agents permission (setup/1-elevenlabs.md). Fix it and run this again."
fi

NUMBERS_OUT="$(hub-phone setup numbers 2>&1)"
COUNT="$(printf '%s' "$NUMBERS_OUT" | grep -c '"phone_number_id"')"
if [ "$COUNT" -eq 0 ]; then
  warn "no phone number is imported into ElevenLabs yet, so no call can go out.
     Do setup/2-twilio.md and setup/3-import-number.md, then run this line again."
elif [ "$COUNT" -eq 1 ]; then
  NUM_ID="$(printf '%s' "$NUMBERS_OUT" | sed -n 's/.*"phone_number_id": *"\([^"]*\)".*/\1/p' | head -1)"
  conf_set NUMBER_ID "$NUM_ID"
  ok "calls go out from the one imported number (ends with $(printf '%s' "$NUMBERS_OUT" | sed -n 's/.*"ends_with": *"\([^"]*\)".*/\1/p' | head -1))"
else
  echo "$NUMBERS_OUT"
  NUM_ID="$(ask "Several numbers are imported. Paste the phone_number_id to call from" "$(conf_get NUMBER_ID)")"
  [ -n "$NUM_ID" ] && conf_set NUMBER_ID "$NUM_ID" && ok "calls go out from $NUM_ID"
fi
systemctl restart hub-phone.service   # the worker reads config.env at start

# --- 5. The recipe in your hub --------------------------------------------------
say "The recipe in your hub"
if id "$AI_USER" >/dev/null 2>&1; then
  AI_HOME="$(getent passwd "$AI_USER" | cut -d: -f6)"
  HUB="${HUB:-$AI_HOME/hub}"
fi
if [ -n "$HUB" ] && [ -d "$HUB" ]; then
  ROOM="$(kb_skills_room "$HUB")"
  install -d -m 755 "$ROOM/phone-errands/templates"
  install -m 644 "$SRC/skill/phone-errands/SKILL.md" "$ROOM/phone-errands/SKILL.md"
  install -m 644 "$SRC/skill/phone-errands/templates/reservation-order.json" "$ROOM/phone-errands/templates/reservation-order.json"
  chown -R "$AI_USER":"$AI_USER" "$ROOM/phone-errands"
  if [ -d "$HUB/.git" ]; then
    su - "$AI_USER" -c "cd '$HUB' && git add skills/phone-errands 2>/dev/null; git add '$ROOM/phone-errands' 2>/dev/null; git -c user.name='hub-phone' -c user.email='hub-phone@localhost' commit -q -m 'Add the phone-errands recipe (hub-phone)' >/dev/null 2>&1" || true
  fi
  ok "phone-errands recipe in $ROOM/phone-errands (your assistant reads that room)"
else
  warn "no hub folder found at ${HUB:-<unknown>}. Copy skill/phone-errands/ into your hub's skills room by hand,
     or run again with HUB=/path/to/hub."
fi

# --- 6. Prove the assistant's path ---------------------------------------------
say "Proof"
if id "$AI_USER" >/dev/null 2>&1; then
  PROOF="$(systemd-run --quiet --property=User="$AI_USER" --property=NoNewPrivileges=yes --pipe --wait /usr/local/bin/hub-phone health 2>&1)"
  if printf '%s' "$PROOF" | grep -q '"worker_recent": true'; then
    ok "as $AI_USER, sandboxed, hub-phone health answers and the worker is alive"
  else
    warn "as $AI_USER the health check did not come back clean:
     $PROOF"
  fi
fi
if printf '%s' "$PROOF" | grep -q '"configured": true'; then
  ok "configured: agent and number are set"
else
  warn "not configured yet: the agent or the number is missing (see above). Orders will be refused until both are set."
fi

# --- 7. One rehearsal, only if you say so ----------------------------------------
say "Rehearsal"
if printf '%s' "${PROOF:-}" | grep -q '"configured": true' && ask_yes "Call your own number now for a one-minute rehearsal? You play the restaurant" "n"; then
  JOB="/tmp/hub-phone-rehearsal-$(date +%Y%m%d-%H%M).json"
  DATE="$(date -d '+7 days' +%F 2>/dev/null || python3 -c 'import datetime;print((datetime.date.today()+datetime.timedelta(days=7)).isoformat())')"
  cat > "$JOB" <<JSON
{
  "job_id": "rehearsal-$(date +%Y%m%d-%H%M)",
  "mode": "rehearsal",
  "to_number": "$OWN",
  "contact": "a rehearsal with yourself: you answer as the restaurant",
  "goal": "Reserve a table for two.",
  "name": "$NAME",
  "opening": "Hello, this is the AI assistant of $NAME. I'd like to reserve a table.",
  "date": "$DATE",
  "time": "19:00",
  "party_size": 2,
  "allowed_changes": "Half an hour earlier or later is fine. No fees or deposits."
}
JSON
  chmod 644 "$JOB"
  SUB="$(su - "$AI_USER" -c "hub-phone submit '$JOB' --authorization 'Rehearsal call requested during install' --source 'install.sh'" 2>&1)"
  JOB_ID="$(printf '%s' "$SUB" | sed -n 's/.*"job_id": *"\([^"]*\)".*/\1/p' | head -1)"
  if [ -n "$JOB_ID" ]; then
    log "Your phone will ring within a few seconds. Answer as a restaurant would. The call ends by itself."
    for i in 1 2 3 4; do
      RES="$(su - "$AI_USER" -c "hub-phone wait '$JOB_ID' --seconds 55" 2>&1)"
      printf '%s' "$RES" | grep -q '"status": "finished"' && break
    done
    echo "$RES"
    log "Above is what the service hands your assistant: the transcript and the instruction to judge it."
  else
    warn "the rehearsal was not queued: $SUB"
  fi
fi

rm -rf "$WORK"
echo
log "Done. Tell your assistant, in Telegram or the desktop app: \"Call +49... and reserve a table for two on Friday at 19:00.\""
log "It reads the phone-errands recipe, places the order, and reports confirmed, declined, not reached, or unclear."
