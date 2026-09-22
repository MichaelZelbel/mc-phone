# 1. ElevenLabs: the voice, and a key with a cap

ElevenLabs runs the voice agent: it listens, thinks with a language model, and speaks. You
need an account, and one API key that the server keeps.

These steps were checked on the ElevenLabs web app in September 2026. Screens change; if a
button is not where this page says, look for the same words nearby, or ask your assistant to
compare this page with what you see.

## The account

1. Go to https://elevenlabs.io and create an account, or sign in.
2. Open **Agents** (in the left menu, or at https://elevenlabs.io/app/agents). You do not
   need to create an agent by hand: the installer makes one called **Godspeed phone** with the
   prompt this add-on ships. If you want to hear how it sounds first, the page has a test
   button once the agent exists.

Which plan you need depends on how many calls you make. Calls are paid in ElevenLabs
credits; a two-minute call cost the author about 1,300 credits plus a few hundred for the
language model. Check the current plan page before you decide; the free tier was enough for
the author's first tests, and the installer does not need any particular plan to run.

## The key

Make a key that can do only what this add-on needs.

1. Open your profile menu, then **API keys** (or https://elevenlabs.io/app/settings/api-keys).
2. **Create API key**. Name it `mc-phone`.
3. Switch **Restrict key** on and give it only the agents permission (the one that lets it
   create and edit agents and make calls; in September 2026 it was called *ElevenAgents*
   with *Write* access). Nothing else.
4. Set a **credit limit** per billing period. The author uses 3,000. That is the most this
   key can spend if something goes wrong.
5. Switch on the option that disables the key automatically if it is found in public.
6. Copy the key. You will paste it once, into the installer, which stores it on the server in
   a file only root can read. Do not put it in your mission control folder, a note, or a chat.

If you lose the key, make a new one here and delete the old one; then delete
`/etc/mc-phone/credentials.env` on the server and run the installer again.

## What ElevenLabs keeps

No audio is recorded: the add-on asks for that on every call and on the agent. The text of
each conversation stays in your ElevenLabs workspace, where you and your assistant read it
back. Once the installer has created the **Godspeed phone** agent, open it, find its privacy or
security settings, and set how many days transcripts are kept. The author set seven. Check
the setting rather than trusting this page: the provider decides what its retention options
mean, and the screen may have changed.
