import { NavLink } from 'react-router'

export default function NavBar() {
  return (
    <nav className="navbar">
      <NavLink to="/" className="app-name">klippbok</NavLink>
      <ul className="nav-links">
        <li>
          <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Gallery
          </NavLink>
        </li>
        <li>
          <NavLink to="/import" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Import
          </NavLink>
        </li>
        <li>
          <NavLink to="/video" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Video
          </NavLink>
        </li>
        <li>
          <NavLink to="/cleanup" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Cleanup
          </NavLink>
        </li>
        <li>
          <NavLink to="/curate" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Curate
          </NavLink>
        </li>
        <li>
          <NavLink to="/crop" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Crop
          </NavLink>
        </li>
        <li>
          <NavLink to="/caption" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Caption
          </NavLink>
        </li>
        <li>
          <NavLink to="/triage" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Triage
          </NavLink>
        </li>
        <li>
          <NavLink to="/export" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Export
          </NavLink>
        </li>
        <li>
          <NavLink to="/settings" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Settings
          </NavLink>
        </li>
      </ul>
    </nav>
  )
}
