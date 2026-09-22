# 4. The first call: a rehearsal with yourself

Before the assistant calls anyone else, let it call you. You answer as the restaurant would.
That is the whole test, and it is the only call the service will ever make without a
specific errand from you.

## When the installer offers it

At the end of the install, after the proof, it asks:

```
[phone] Call your own number now for a one-minute rehearsal? You play the restaurant (y/n) [n]:
```

Say `y`. Your phone rings within a few seconds, from your own number. Pick up and say what a
restaurant says: "Sam's Bistro, hello?" Then let it happen.

## What you should hear

- It waits for you to speak first. If you say nothing, it waits; after thirty seconds of
  silence it hangs up.
- Then, once: "Hello, this is the AI assistant of <your name>. I'd like to reserve a table."
  Nothing more. No date, no time, no number of people until you ask.
- Ask "For when?" and it gives the date and time from the order. Ask "How many?" and it says
  two. Ask for a name and it gives yours. Ask for a number to call back and it reads yours,
  digit by digit.
- Tell it "Seven is full, would half past seven do?" and it accepts, because the order
  allowed half an hour either way. Tell it "We need a deposit" and it says it has to take
  that back to you, and ends politely.
- Ask "Am I talking to a computer?" and it says yes, plainly, and returns to the errand.
- Say goodbye and it hangs up.

The installer then prints what the service hands your assistant: the transcript, and the
instruction to judge it rather than trust the word "done".

## Later, by hand

A rehearsal can be repeated any time. Copy `skill/phone-errands/templates/reservation-order.json`,
set `"mode": "rehearsal"` and `"to_number"` to your own number, and run on the server as your
assistant's account:

```
mc-phone submit order.json --authorization "rehearsal" --source "by hand"
mc-phone wait <job_id>
```

A rehearsal refuses every number but your own. That is deliberate.

## If the phone does not ring

`mc-phone result <job_id>` shows what the provider said. The two causes the author met: the
Twilio identity check was not yet approved (a `401` from the provider), and the two accounts
were fine but the call ended after thirty seconds because nobody spoke. Neither is fixed by
calling again; fix the cause, then queue a new order with a new `job_id`.
