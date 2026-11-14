import { act, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { updateUrl, useUrlSearch } from '../url-state'

function LocationView() {
  return <output aria-label="当前地址">{useUrlSearch()}</output>
}
it('preserves the selected session and snapshot across page changes and popstate', () => {
  window.history.replaceState({}, '', '/?session=s1&snapshot=frozen')
  render(<LocationView />)
  act(() => updateUrl({ page: 'library', q: '诸葛亮' }))
  expect(screen.getByLabelText('当前地址')).toHaveTextContent('session=s1')
  expect(new URLSearchParams(window.location.search).get('q')).toBe('诸葛亮')
  act(() => {
    window.history.replaceState({}, '', '/?page=chat&session=s2')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  expect(screen.getByLabelText('当前地址')).toHaveTextContent('session=s2')
})
