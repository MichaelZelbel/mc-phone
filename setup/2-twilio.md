# 2. Twilio: the phone line

Twilio is the phone company in this setup. ElevenLabs makes the conversation; Twilio puts it
on a real line and shows your own mobile number to the person who answers. You need an
account with a small balance, an identity check, and your own number verified as the number
calls come from.

Checked in September 2026 on a German account. Other countries differ in what the identity
check asks for; the shape of the steps is the same.

## The account

1. Go to https://www.twilio.com and create an account, or sign in at
   https://console.twilio.com.
2. Confirm your email and your phone number as the sign-up asks.
3. **Upgrade** the account and add a payment method. A trial account can call only numbers
   you have verified, and the restaurant is not one of them. Twilio is pay as you go; the
   author put in twenty US dollars. Look up the per-minute rate for calls in your country on
   Twilio's price page before you decide how much to add.
4. Complete the **regulatory compliance** or **identity** step for your country when Twilio
   asks for it. For Germany the author's individual profile had to show *Approved* before an
   outgoing call worked; before that, calls failed with a permission error that says nothing
   about identity. If your first call fails with an error like `401`, look here first.

## Your own number as the caller ID

The person you call sees a number. This add-on uses your own mobile number, so a call-back
reaches you and nobody has to buy a second number.

1. In the console, open **Phone Numbers**, then **Manage**, then **Verified Caller IDs**.
2. **Add a new Caller ID**, enter your mobile number in international form (`+49...`).
3. Twilio calls or texts you a code. Text verification was not offered for the author's
   German number; the call was. If your phone shows an incoming call as a small banner, the
   keypad may not be reachable in time: the author had to switch his phone to show calls
   full screen before the digits went through. Type the code as the call asks.
4. The number now appears under Verified Caller IDs. That is all Twilio needs to know.

## What you take to the next page

From the console's home page, note your **Account SID** and **Auth Token** (the token is
hidden behind a *show* button). You will paste both into ElevenLabs on the next page, and
nowhere else. Neither goes into your mission control or into the installer.
