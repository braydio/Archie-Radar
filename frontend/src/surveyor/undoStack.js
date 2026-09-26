import { computed, ref } from 'vue'

export function createUndoStack() {
  const undoCommands = ref([])
  const redoCommands = ref([])
  const busy = ref(false)
  const canUndo = computed(() => undoCommands.value.length > 0 && !busy.value)
  const canRedo = computed(() => redoCommands.value.length > 0 && !busy.value)

  function record(command) {
    undoCommands.value.push(command)
    redoCommands.value = []
  }
  async function run(from, to, direction) {
    if (busy.value || !from.value.length) return
    const command = from.value.pop()
    busy.value = true
    try {
      await command[direction]()
      to.value.push(command)
    } catch (error) {
      from.value.push(command)
      throw error
    } finally { busy.value = false }
  }
  return { canUndo, canRedo, record, undo: () => run(undoCommands, redoCommands, 'undo'), redo: () => run(redoCommands, undoCommands, 'redo') }
}
