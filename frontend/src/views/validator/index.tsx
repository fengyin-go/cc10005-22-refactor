import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/validator'
const columns = [
  "规则编号",
  "校验对象",
  "校验类型",
  "校验表达式",
  "期望值范围",
  "采样比例",
  "异常阈值",
  "阻断级别"
]
const actions = [
  "提交校验",
  "启用规则",
  "停用规则"
]
const statuses = [
  "草稿",
  "待校验",
  "已启用",
  "已停用"
]
const stats = [
  {
    "label": "校验规则总数",
    "value": 0
  },
  {
    "label": "已启用规则",
    "value": 0
  },
  {
    "label": "待校验规则",
    "value": 0
  }
]

type Row = Record<string, unknown>

type FieldRelation = {
  状态: string
  字段编号: string | null
  引用文本: string | null
  说明: string
}

function renderPresence(row: Row, field: string) {
  const state = (row.字段状态 as Record<string, string> | undefined)?.[field]
  if (state === '显式空值') {
    return <span className="presence-tag">显式空值</span>
  }
  if (state === '未提供') {
    return <span className="presence-tag muted">未提供</span>
  }
  const value = row[field]
  return <>{value === null || value === undefined || value === '' ? '—' : String(value)}</>
}

function renderRelation(row: Row) {
  const relation = row.校验对象关系 as FieldRelation | undefined
  const name = renderPresence(row, '校验对象')
  if (!relation) {
    return <div className="relation-cell">{name}</div>
  }
  return (
    <div className="relation-cell">
      <div className="relation-name">{name}</div>
      <span className={`relation-tag ${relation.状态 === '已关联' ? 'linked' : 'pending'}`}>
        {relation.状态}
      </span>
      {relation.字段编号 ? <span className="relation-id">{relation.字段编号}</span> : null}
      {relation.状态 !== '已关联' ? (
        <span className="relation-note">{relation.说明}</span>
      ) : null}
    </div>
  )
}

export default function ValidatorView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('校验规则列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '结果校验列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(action: string, row: Row) {
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ values: { action } }),
      })
      if (!response.ok) {
        throw new Error('结果校验动作未生效，请稍后重试')
      }
      const payload = await response.json()
      if (!payload.ok) {
        throw new Error(payload.message || '结果校验动作被拒绝')
      }
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '结果校验操作失败')
    }
  }

  async function confirmRelation(row: Row) {
    setErrorMessage('')
    const raw = window.prompt('请输入共享字段登记册中的校验对象编号（例如 FLD-RECORD-COUNT）', '')
    if (!raw) {
      return
    }
    try {
      const response = await request(`${ENDPOINT}/${row.id}/relations`, {
        method: 'POST',
        body: JSON.stringify({ values: { 校验对象编号: raw.trim() } }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || '引用关系确认失败')
      }
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '引用关系确认失败')
    }
  }

  return (
    <section className="page" data-module="validator">
      <header className="page-head">
        <div>
          <h2>结果校验管理</h2>
          <p className="page-desc">维护结果校验规则的输入、执行约束与结果记录，为结果校验提供可验证的数据工程流程。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('校验规则登记入口尚未接入审批流')}>
            登记校验规则
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出结果校验清单
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => (
                <td key={column}>
                  {column === '校验对象' ? renderRelation(row) : renderPresence(row, column)}
                </td>
              ))}
              <td className="row-actions">
                {actions.map((action) => (
                  <button key={action} className="link" type="button" onClick={() => void runAction(action, row)}>
                    {action}
                  </button>
                ))}
                {(row.校验对象关系 as FieldRelation | undefined)?.状态 !== '已关联' && (
                  <button className="link" type="button" onClick={() => void confirmRelation(row)}>
                    确认引用
                  </button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无结果校验数据，可先登记校验规则</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条结果校验记录</span>
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
