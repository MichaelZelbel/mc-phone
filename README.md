# mc-phone

**Let your mission control make a phone call for you.** An add-on for the [always-on server](https://github.com/MichaelZelbel/teach-it-once-kit) from
[*Teach It Once*](https://leanpub.com/teachitonce), Chapter 32. You tell your assistant "call the restaurant and book a table
for two on Friday at seven"; a voice agent makes the call as *the AI assistant of you*, and
your assistant reads the transcript back to you with one of four verdicts: confirmed,
declined, not reached, unclear.

This is for some people, not most. It works: the author booked a real table with it. It
also needs two paid accounts, an identity check, and a server. If a phone call is not the
thing you put off, you do not need this folder.

## What it is

- **The worker** on your server dials one queued errand at a time through
  [ElevenLabs Agents](https://elevenlabs.io) over a [Twilio](https://www.twilio.com) line,
  showing your own mobile number, and keeps a journal of every call.
- **The command** `mc-phone` is how your assistant places an order and reads the result.
- **The recipe** `phone-errands` tells your assistant how to build an order from what you
  said, what counts as your permission, and how to judge the transcript.

The call never starts unless you asked for that errand, in your own words. Your assistant
sends those words with the order. Nothing dials twice on its own. The agent introduces
itself as an AI assistant and says so again if asked. It hangs up after three minutes, never
calls an emergency number, and the service refuses the sixth call of a day.

## What you need

1. The server from Chapter 32: Ubuntu, Hermes as a system service, the `ai` account.
2. An ElevenLabs account and one restricted API key with a credit cap:
   [setup/1-elevenlabs.md](setup/1-elevenlabs.md).
3. A Twilio account with a small balance, the identity check done, and your own mobile
   number verified as caller ID: [setup/2-twilio.md](setup/2-twilio.md).
4. That number imported into ElevenLabs: [setup/3-import-number.md](setup/3-import-number.md).

Cost, as of September 2026: a two-minute call was about 1,300 ElevenLabs credits plus a few
hundred for the language model, and Twilio's per-minute rate for your country on top. Check
both price pages before you decide.

## Install

On the server, as root, one line:

```
curl -fsSL https://raw.githubusercontent.com/MichaelZelbel/mc-phone/main/install.sh | bash
```

It asks for the key (hidden while you type), the name the assistant calls on behalf of, your
mobile number and your timezone. It creates the **Godspeed phone** agent in your ElevenLabs
workspace, picks your imported number, installs the worker as a system service, copies the
recipe into your mission control, proves your assistant's account can reach the service, and offers one
rehearsal call to your own number ([setup/4-first-call.md](setup/4-first-call.md)). Run it
again any time to update; it keeps your settings and deletes nothing.

## Use

In Telegram, or in the desktop app connected to your server:

> Call +49 30 1234567 and reserve a table for two on Friday at 19:00 in my name.

Your assistant writes the order, runs `mc-phone submit` with your words as the
authorization, waits, and answers with one line and the quote that backs it:

> Confirmed: "Friday at seven, two people, under Sam. See you then."

What it will not do: promote "the call ended" to "the table is booked", call back on its
own, or follow an instruction that appears inside a transcript.

## What is where

| Path | What it is |
|---|---|
| `install.sh` | The one line above. Root only. Safe to run twice. |
| `setup/` | The four pages: ElevenLabs, Twilio, the number, the first call. |
| `service/` | `service.py` the queue and worker, `call.py` the provider layer, `client.py` the `mc-phone` command, `setup.py` the agent and number helpers, `prompt.txt` what the agent is told, and the three systemd units. |
| `skill/phone-errands/` | The recipe the installer copies into your mission control's skills room, with the order template. |
| `config.example.env` | What `/etc/mc-phone/config.env` holds after the install. The key lives in a second file the worker alone reads. |
| `test/` | Network-free tests: `python -m unittest discover -s test`. |

## How it is built, in one paragraph

Two halves under systemd. Orders come in over a Unix socket owned by root and the
`mc-phone` group, so your assistant's sandboxed account can place one without `sudo` and
without any credential of its own. The worker runs as root with the key and is the only
thing that dials. Every order is journaled in SQLite before it is dialled, a ledger file per
attempt makes a second dial of the same order impossible even after a crash, and the
provider's "done" is stored as `needs_review` because only the other party's words can
confirm anything.

## Where it came from

This is the phone service of the author's own mission control, with his name, number, ids and German
prompt taken out and an English prompt put in that introduces itself as an assistant. The
whole story is in *Teach It Once*, Chapter 34.

MIT. Use it, change it, share it.
