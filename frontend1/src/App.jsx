import { useEffect, useState } from "react";
import { Routes, Route, Link, useNavigate } from "react-router-dom";
import "./App.css";

import Layout from "./components/Layout";
import OnboardingPage from "./pages/OnboardingPage";
import SignInPage from "./pages/SignInPage";
import ChatInterviewPage from "./pages/ChatInterviewPage";
import DsaSheetPage from "./pages/DsaSheetPage";
import CoreCsPage from "./pages/CoreCsPage";
import CompaniesPage from "./pages/CompaniesPage";
import CompanyDetailPage from "./pages/CompanyDetailPage";
import MktPage from "./pages/MktPage";
import WhiteboardPage from "./pages/WhiteboardPage";
import CodingPage from "./pages/CodingPage";
import AptitudePage from "./pages/AptitudePage";
import ProfilePage from "./pages/ProfilePage";

import { ensureIdentity } from "./services/auth";

function App() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [onboarded, setOnboarded] = useState(() => localStorage.getItem("iq_onboarded") === "true");

  const completeOnboarding = () => {
    localStorage.setItem("iq_onboarded", "true");
    setOnboarded(true);
    navigate("/");
  };

  useEffect(() => {
    ensureIdentity().finally(() => setReady(true));
  }, []);

  if (!ready) {
    return (
      <div className="layout" style={{ alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: "var(--muted)" }}>Loading InterviewIQ...</p>
      </div>
    );
  }

  return (
    <Routes>
      {/* These two are always reachable by route, with no sidebar, even
          before onboarding completes — so links to them from inside
          OnboardingPage (Sign In) actually navigate instead of being
          swallowed by the "not onboarded yet" gate below. */}
      <Route path="/onboarding" element={<OnboardingPage onComplete={completeOnboarding} />} />
      <Route path="/sign-in" element={<SignInPage />} />

      <Route
        path="/*"
        element={
          !onboarded ? (
            <OnboardingPage onComplete={completeOnboarding} />
          ) : (
            <Layout>
              <Routes>
                <Route path="/" element={<ChatInterviewPage />} />
                <Route path="/dsa-sheet" element={<DsaSheetPage />} />
                <Route path="/core-cs" element={<CoreCsPage />} />
                <Route path="/companies" element={<CompaniesPage />} />
                <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
                <Route path="/mkt" element={<MktPage />} />
                <Route path="/design" element={<WhiteboardPage />} />
                <Route path="/code" element={<CodingPage />} />
                <Route path="/code/:problemId" element={<CodingPage />} />
                <Route path="/aptitude" element={<AptitudePage />} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route
                  path="*"
                  element={
                    <div className="page-content" style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
                      <h1 style={{ fontSize: 24, marginBottom: 10 }}>Page not found</h1>
                      <p style={{ color: "var(--muted)", marginBottom: 20 }}>That route doesn't exist.</p>
                      <Link to="/" style={{ color: "var(--primary)", fontWeight: 600 }}>Go home &rarr;</Link>
                    </div>
                  }
                />
              </Routes>
            </Layout>
          )
        }
      />
    </Routes>
  );
}

export default App;
