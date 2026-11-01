<script setup lang="ts">
import { auth } from "../lib/auth";
</script>

<template>
  <div class="page help">
    <h1>Get support</h1>

    <section class="urgent">
      <h2>If someone may be in danger</h2>
      <ul>
        <li><strong>Overdose or medical emergency:</strong> call <a href="tel:911">911</a> or your local emergency number. If you have naloxone and it may be an opioid overdose, give it and stay with the person.</li>
        <li><strong>Thoughts of suicide or crisis (US):</strong> call or text <a href="tel:988">988</a>.</li>
        <li><strong>Severe withdrawal:</strong> seizures, confusion, hallucinations or chest pain need emergency care now.</li>
      </ul>
    </section>

    <section>
      <h2>Talk to someone</h2>
      <ul>
        <li><strong>SAMHSA National Helpline (US):</strong> <a href="tel:18006624357">1-800-662-4357</a>. Free, confidential, open 24 hours, for treatment referrals and information.</li>
        <li><strong>Quit smoking or vaping (US):</strong> <a href="tel:18007848669">1-800-784-8669</a>.</li>
        <li><strong>Gambling (US):</strong> <a href="tel:18006973738">1-800-MY-RESET (1-800-697-3738)</a>.</li>
        <li><strong>Outside the US:</strong> your doctor or local health service can direct you to support nearby.</li>
      </ul>
    </section>

    <section>
      <h2>Stopping safely</h2>
      <p><strong>Alcohol and benzodiazepines:</strong> if you use them daily or heavily, stopping or sharply cutting back can cause seizures and can be fatal. A clinician can help you taper or detox safely.</p>
      <p><strong>Opioids:</strong> tolerance falls quickly after cutting back, so an old dose can become an overdose. Medications such as buprenorphine and methadone greatly lower that risk. Keep naloxone on hand.</p>
      <p><strong>Prescribed medication:</strong> talk to your prescriber before changing how you take it.</p>
    </section>

    <section>
      <h2>Using this app</h2>
      <p>Levels are a pace you set yourself, not medical advice. They aren't offered for alcohol, benzodiazepines or opioids, because tapering those safely needs a clinician. If stepping down makes you unwell, move your limit back up in Settings and talk to a clinician. Nothing is lost.</p>
      <p>Habit Helper is a personal log. It doesn't diagnose, treat or give dosing advice, and any limit you set is your own, not a safe level. A log is only information. A day over your limit doesn't erase your progress, and it can show you what to plan for next time.</p>
    </section>

    <p class="footer-links">
      <RouterLink :to="auth.username ? '/' : '/login'">{{ auth.username ? "Back to Today" : "Back to log in" }}</RouterLink>
    </p>
  </div>
</template>
