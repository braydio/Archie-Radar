<script setup>
import { reactive, ref } from 'vue'
const props = defineProps({ object: { type: Object, required: true } })
const emit = defineEmits(['save', 'cancel'])
const defaults = {
  access: ['Follow up with property', 'contact'], trail_camera: ['Check camera', 'camera'],
  evidence: ['Re-check evidence', 'evidence'], zone: [props.object.subtype === 'needs_search' ? 'Search this area' : 'Re-check this area', props.object.subtype === 'needs_search' ? 'search' : 'recheck'],
  corridor: ['Review corridor', 'recheck'],
}
const [title, task_type] = defaults[props.object.object_type] || ['Follow up on field object', 'other']
const form = reactive({ title, task_type, priority: 'normal', due_at: '', notes: '' })
const dueChoice = ref('none')
const customDue = ref(false)
function localInputValue(date) {
  const pad = value => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
function chooseDue(choice) {
  dueChoice.value = choice; customDue.value = choice === 'custom'
  if (choice === 'none') form.due_at = ''
  else if (choice === 'custom') return
  else {
    const due = new Date()
    if (choice === 'tomorrow') due.setDate(due.getDate() + 1)
    if (choice === 'tonight') due.setHours(21, 0, 0, 0)
    else if (choice === 'today') due.setHours(23, 59, 0, 0)
    else due.setHours(12, 0, 0, 0)
    form.due_at = localInputValue(due)
  }
}
function submit() { emit('save', { ...form, map_object_id: props.object.id, due_at: form.due_at ? new Date(form.due_at).toISOString() : null }) }
</script>
<template>
  <form class="field-sheet task-editor" @submit.prevent="submit">
    <header><div><p class="eyebrow">SURVEYOR · FOLLOW-UP</p><h2>Add follow-up</h2></div><button type="button" aria-label="Cancel" @click="emit('cancel')">×</button></header>
    <label>Title<input v-model="form.title" required maxlength="240" /></label>
    <label>Type<select v-model="form.task_type"><option value="search">Search</option><option value="recheck">Re-check</option><option value="contact">Contact</option><option value="camera">Camera</option><option value="trap">Trap</option><option value="evidence">Evidence</option><option value="flyer">Flyer</option><option value="candidate">Candidate</option><option value="other">Other</option></select></label>
    <label>Priority<select v-model="form.priority"><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
    <fieldset class="task-due-options"><legend>Due</legend><div><button v-for="choice in [['tonight','Tonight'],['today','Today'],['tomorrow','Tomorrow'],['custom','Custom'],['none','No date']]" :key="choice[0]" type="button" :class="{ active: dueChoice === choice[0] }" @click="chooseDue(choice[0])">{{ choice[1] }}</button></div><label v-if="customDue">Custom date<input v-model="form.due_at" type="datetime-local" /></label></fieldset>
    <label>Notes<textarea v-model="form.notes" rows="3"></textarea></label>
    <footer><button type="button" class="secondary-button" @click="emit('cancel')">Cancel</button><button class="primary">Save follow-up</button></footer>
  </form>
</template>
