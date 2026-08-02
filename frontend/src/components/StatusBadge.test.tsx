import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './ui'

describe('StatusBadge', () => {
  it('renders Traditional Chinese state labels', () => {
    render(<StatusBadge status="running" />)
    expect(screen.getByText('執行中')).toBeInTheDocument()
  })
})
