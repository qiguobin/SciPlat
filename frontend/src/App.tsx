import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectDetail from './pages/ProjectDetail'
import Papers from './pages/Papers'
import PaperDetail from './pages/PaperDetail'
import Materials from './pages/Materials'
import References from './pages/References'
import Search from './pages/Search'
import Schedule from './pages/Schedule'
import Timeline from './pages/Timeline'
import Ideas from './pages/Ideas'
import Achievements from './pages/Achievements'
import Canvas from './pages/Canvas'
import Tracking from './pages/Tracking'
import Island from './pages/Island'
import AiStatus from './pages/AiStatus'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="projects" element={<Projects />} />
          <Route path="projects/:id" element={<ProjectDetail />} />
          <Route path="papers" element={<Papers />} />
          <Route path="papers/:id" element={<PaperDetail />} />
          <Route path="materials" element={<Materials />} />
          <Route path="materials/:sub" element={<Materials />} />
          <Route path="references" element={<Navigate to="/references/list" replace />} />
          <Route path="references/:sub" element={<References />} />
          <Route path="schedule" element={<Navigate to="/schedule/calendar" replace />} />
          <Route path="schedule/:sub" element={<Schedule />} />
          <Route path="timeline" element={<Timeline />} />
          <Route path="ideas" element={<Ideas />} />
          <Route path="achievements" element={<Navigate to="/achievements/list" replace />} />
          <Route path="achievements/:sub" element={<Achievements />} />
          <Route path="canvas" element={<Canvas />} />
          <Route path="tracking" element={<Tracking />} />
          <Route path="island" element={<Island />} />
          <Route path="ai-status" element={<Navigate to="/ai-status/overview" replace />} />
          <Route path="ai-status/:sub" element={<AiStatus />} />
          <Route path="search" element={<Search />} />
          <Route path="*" element={<Dashboard />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
