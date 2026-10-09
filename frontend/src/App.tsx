import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Incidents from './pages/Incidents'
import IncidentDetail from './pages/IncidentDetail'
import Graph from './pages/Graph'
import GraphBuild from './pages/GraphBuild'
import GraphTopology from './pages/GraphTopology'
import Workflow from './pages/Workflow'
import Services from './pages/Services'
import UserManagement from './pages/UserManagement'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/incidents/:id" element={<IncidentDetail />} />
        <Route path="/graph" element={<Graph />} />
        <Route path="/graph/build" element={<GraphBuild />} />
        <Route path="/graph/topology" element={<GraphTopology />} />
        <Route path="/workflow" element={<Workflow />} />
        <Route path="/services" element={<Services />} />
        <Route path="/admin/users" element={<UserManagement />} />
      </Routes>
    </BrowserRouter>
  )
}
