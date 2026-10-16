export type Basic = { age: string; has_diabetes: string }
export const validBasic = (row?: Basic) => Boolean(row && row.age.trim() !== '' && Number.isFinite(Number(row.age)) && Number(row.age) >= 0 && ['0', '1'].includes(row.has_diabetes))
