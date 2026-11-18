import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, it } from 'vitest'
import Dialog from '../dialog'

function DialogHarness() {
  const [isOpen, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        打开确认
      </button>
      {isOpen && (
        <Dialog label="核对反馈" onClose={() => setOpen(false)}>
          <button type="button" data-initial-focus>
            返回检查
          </button>
          <button type="button">确认保存</button>
        </Dialog>
      )}
    </>
  )
}
it('focuses the safe action, wraps Tab and restores the trigger after Escape', async () => {
  const user = userEvent.setup()
  render(<DialogHarness />)
  const trigger = screen.getByRole('button', { name: '打开确认' })
  await user.click(trigger)
  expect(screen.getByRole('dialog', { name: '核对反馈' })).toBeVisible()
  expect(screen.getByRole('button', { name: '返回检查' })).toHaveFocus()
  await user.tab({ shift: true })
  expect(screen.getByRole('button', { name: '确认保存' })).toHaveFocus()
  await user.tab()
  expect(screen.getByRole('button', { name: '返回检查' })).toHaveFocus()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})
it('does not dismiss a saving dialog on Escape', async () => {
  const user = userEvent.setup()
  let closed = false
  render(
    <Dialog
      label="保存中"
      isDismissable={false}
      onClose={() => {
        closed = true
      }}
    >
      <button type="button" data-initial-focus>
        正在保存
      </button>
    </Dialog>,
  )
  await user.keyboard('{Escape}')
  expect(closed).toBe(false)
})
