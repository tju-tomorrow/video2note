<script setup lang="ts">
defineProps<{
  title: string;
}>();
</script>

<template>
  <header class="window-chrome" role="presentation">
    <div class="window-chrome__drag">
      <span class="window-chrome__title">{{ title }}</span>
    </div>
  </header>
</template>
