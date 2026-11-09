import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setOperatorHeader } from '../api/client'
import type { Person } from '../api/types'

/**
 * 目前操作者。系統不登入，操作者從設定頁的名單選擇，用來記錄是誰做的。
 * 選擇只記在這台電腦的瀏覽器（localStorage），不是帳號。
 */

const KEY = 'kidney-operator'

interface OperatorState {
  operator: string
  people: Person[]
  physicians: Person[]
  setOperator: (name: string) => void
  reloadPeople: () => Promise<void>
}

const Ctx = createContext<OperatorState | null>(null)

const readStored = () => {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

export function OperatorProvider({ children }: { children: ReactNode }) {
  const [operator, setOperatorState] = useState(readStored)
  const [people, setPeople] = useState<Person[]>([])

  const reloadPeople = useCallback(async () => {
    try {
      const res = await api.get<{ people: Person[] }>('/people')
      setPeople(res.people)
    } catch {
      // 後端未啟動時名單為空，介面仍可瀏覽
    }
  }, [])

  useEffect(() => {
    void reloadPeople()
  }, [reloadPeople])

  useEffect(() => {
    setOperatorHeader(operator)
  }, [operator])

  const setOperator = useCallback((name: string) => {
    setOperatorState(name)
    setOperatorHeader(name)
    try {
      localStorage.setItem(KEY, name)
    } catch {
      // 無法寫入時只保留在這次瀏覽
    }
  }, [])

  const value = useMemo(
    () => ({
      operator,
      people,
      physicians: people.filter((p) => p.kind === 'physician' && p.active),
      setOperator,
      reloadPeople,
    }),
    [operator, people, setOperator, reloadPeople],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useOperator() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useOperator 必須在 OperatorProvider 內使用')
  return v
}
