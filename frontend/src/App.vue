<script setup lang="ts">
import { auth } from "./lib/auth";
</script>

<template>
  <a class="skip" href="#main">Skip to content</a>
  <nav v-if="auth.username" class="nav" aria-label="Main">
    <RouterLink to="/">Today</RouterLink>
    <RouterLink to="/trends">Trends</RouterLink>
    <RouterLink to="/history">History</RouterLink>
    <RouterLink to="/settings">Settings</RouterLink>
  </nav>
  <main id="main"><RouterView /></main>
</template>
