import { NavLink } from 'react-router'

export default function NavBar() {
  return (
    <nav className="navbar">
      <span className="app-name">klippbok</span>
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
          <NavLink to="/crop" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Crop
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
