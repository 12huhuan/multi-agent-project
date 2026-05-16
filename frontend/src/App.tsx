import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ListingPage from "./pages/ListingPage";
import CustomerServicePage from "./pages/CustomerServicePage";
import DashboardPage from "./pages/DashboardPage";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/listing" element={<ListingPage />} />
        <Route path="/customer-service" element={<CustomerServicePage />} />
        <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
      </Route>
    </Routes>
  );
}
