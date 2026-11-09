import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import { Circle } from './pages/Circle'
import { Colors } from './pages/Colors'
import { Home } from './pages/Home'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/circle/:id" element={<Circle />} />
        <Route path="/colors" element={<Colors />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
