import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ListingPage from "./pages/ListingPage";
import CustomerServicePage from "./pages/CustomerServicePage";
import DashboardPage from "./pages/DashboardPage";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";
import ReviewsPage from "./pages/ReviewsPage";
import SocialMediaPage from "./pages/SocialMediaPage";
import SelectionPage from "./pages/SelectionPage";
import CompliancePage from "./pages/CompliancePage";
import OrchestratorPage from "./pages/OrchestratorPage";
import PublishedFeedPage from "./pages/PublishedFeedPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/listing" element={<ListingPage />} />
        <Route path="/customer-service" element={<CustomerServicePage />} />
        <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
        <Route path="/reviews" element={<ReviewsPage />} />
        <Route path="/social" element={<SocialMediaPage />} />
        <Route path="/selection" element={<SelectionPage />} />
        <Route path="/compliance" element={<CompliancePage />} />
        <Route path="/orchestrator" element={<OrchestratorPage />} />
        <Route path="/feed" element={<PublishedFeedPage />} />
      </Route>
    </Routes>
  );
}
