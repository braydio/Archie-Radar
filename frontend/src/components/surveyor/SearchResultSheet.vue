<script setup>
import { reactive } from 'vue'
const emit = defineEmits(['save', 'cancel'])
const form = reactive({ result_summary: 'No cat activity reported', notes: '', outcome: 'no_activity' })
</script>
<template>
  <form class="field-sheet" @submit.prevent="emit('save', { ...form })"><header><div><p class="eyebrow">SEARCH SESSION</p><h2>Finish search</h2></div><button type="button" aria-label="Cancel" @click="emit('cancel')">×</button></header>
    <label>Outcome<select v-model="form.outcome"><option value="no_activity">No activity</option><option value="possible_evidence">Possible evidence</option><option value="camera_maintenance">Camera maintenance</option><option value="follow_up_needed">Follow-up needed</option><option value="other">Other</option></select></label>
    <label>Result summary<input v-model="form.result_summary" maxlength="500" /></label><label>Notes<textarea v-model="form.notes" rows="4"></textarea></label>
    <footer><button type="button" class="secondary-button" @click="emit('cancel')">Cancel</button><button class="primary" type="submit">Save search</button></footer>
  </form>
</template>
