import Sidebar from "./SideBar";

export default function Layout({ children }) {
  return (
    <div className="layout">
      <Sidebar />
      {children}
    </div>
  );
}
