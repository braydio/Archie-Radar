import test from 'node:test'
import assert from 'node:assert/strict'
import { clientPrioritize } from './reviewOrder.js'

const defaults = { sex: 'male', color: 'orange', pattern: 'striped', coat: 'short', altered: 'neutered', collar: 'none',
  microchip: 'none', whiteChest: 'yes', whiteBelly: 'any', whitePaws: 'any', whiteFace: 'any', ageCompatible: false,
  archieCompatible: false, traitMode: 'prioritize' }

test('default Archie prioritization leaves authoritative server order intact', () => {
  const rows = [{ id: 2, match_score: 41 }, { id: 1, match_score: 88 }]
  assert.equal(clientPrioritize(rows, defaults, 'smart'), rows)
})

test('custom traits only break ties inside score bands', () => {
  const rows = [
    { id: 'low', match_score: 31, sex: 'female', parsed_traits: { colors: ['orange'] } },
    { id: 'high', match_score: 68, sex: 'male', parsed_traits: {} }
  ]
  assert.deepEqual(clientPrioritize(rows, { ...defaults, color: 'black' }, 'smart').map(row => row.id), ['high', 'low'])
})

test('pure sort modes are not client reordered', () => {
  const rows = [{ id: 1, match_score: 2 }, { id: 2, match_score: 99 }]
  assert.equal(clientPrioritize(rows, { ...defaults, color: 'black' }, 'newest'), rows)
})
