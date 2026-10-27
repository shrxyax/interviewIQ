import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, Link, useNavigate } from "react-router-dom";
import "./App.css";

import Layout from "./components/Layout";
import OnboardingPage from "./pages/OnboardingPage";
import SignInPage from "./pages/SignInPage";
import ChatInterviewPage from "./pages/ChatInterviewPage";
import { LoadingState } from "./components/shared/LoadingState";

// Secondary pages are code-split so the heavy editors (Monaco, React Flow,
// Recharts) only download when their route is opened.
const DsaSheetPage = lazy(() => import("./pages/DsaSheetPage"));
const CoreCsPage = lazy(() => import("./pages/CoreCsPage"));
const CoreCsTopicPage = lazy(() => import("./pages/CoreCsTopicPage"));
const CompaniesPage = lazy(() => import("./pages/CompaniesPage"));
const CompanyDetailPage = lazy(() => import("./pages/CompanyDetailPage"));
const MktPage = lazy(() => import("./pages/MktPage"));
const WhiteboardPage = lazy(() => import("./pages/WhiteboardPage"));
const CodingPage = lazy(() => import("./pages/CodingPage"));
const AptitudePage = lazy(() => import("./pages/AptitudePage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));

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
      <div className="layout app-boot">
        <p className="muted">Loading InterviewIQ...</p>
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
              <Suspense fallback={<LoadingState />}>
              <Routes>
                <Route path="/" element={<ChatInterviewPage />} />
                <Route path="/dsa-sheet" element={<DsaSheetPage />} />
                <Route path="/core-cs" element={<CoreCsPage />} />
                <Route path="/core-cs/:noteId" element={<CoreCsTopicPage />} />
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
                    <div className="page-content not-found">
                      <h1>Page not found</h1>
                      <p className="muted">That route doesn't exist.</p>
                      <Link to="/" className="link-btn">Go home &rarr;</Link>
                    </div>
                  }
                />
              </Routes>
              </Suspense>
            </Layout>
          )
        }
      />
    </Routes>
  );
}

export default App;
