import { act, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useQuery, useQueryClient } from '@/lib/query'
import AppQueryProvider from '@/lib/query/provider'

interface AccountViewProps {
  identity: string
  load: () => Promise<string>
}
function AccountView({ identity, load }: AccountViewProps) {
  const query = useQuery({ queryKey: ['account', identity], queryFn: load })
  const client = useQueryClient()
  return (
    <>
      <output aria-label="账户结果">{query.data ?? '正在载入'}</output>
      <button
        type="button"
        onClick={() =>
          void client.invalidateQueries({ queryKey: ['account', identity] })
        }
      >
        刷新账户
      </button>
    </>
  )
}
it('keeps cached content visible while a refresh is pending', async () => {
  let finish: (value: string) => void = () => {}
  const load = vi
    .fn()
    .mockResolvedValueOnce('已加载内容')
    .mockImplementationOnce(
      () =>
        new Promise<string>((resolve) => {
          finish = resolve
        }),
    )
  render(
    <AppQueryProvider>
      <AccountView identity="alice" load={load} />
    </AppQueryProvider>,
  )
  await screen.findByText('已加载内容')
  await act(async () => screen.getByRole('button').click())
  expect(screen.getByLabelText('账户结果')).toHaveTextContent('已加载内容')
  await act(async () => finish('更新后的内容'))
  expect(await screen.findByText('更新后的内容')).toBeVisible()
})
it('does not expose the previous identity cache when switching accounts', async () => {
  const { rerender } = render(
    <AppQueryProvider key="alice">
      <AccountView identity="alice" load={async () => 'Alice私有记录'} />
    </AppQueryProvider>,
  )
  await screen.findByText('Alice私有记录')
  let finish: (value: string) => void = () => {}
  rerender(
    <AppQueryProvider key="bob">
      <AccountView
        identity="bob"
        load={() =>
          new Promise<string>((resolve) => {
            finish = resolve
          })
        }
      />
    </AppQueryProvider>,
  )
  expect(screen.queryByText('Alice私有记录')).not.toBeInTheDocument()
  await act(async () => finish('Bob私有记录'))
  expect(await screen.findByText('Bob私有记录')).toBeVisible()
})
