import { Header } from '@/components/Header';
import { MainframeNav } from '@/components/MainframeNav';

export default function MainframeLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-darkBg text-gray-100 flex flex-col">
      <Header />
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Mainframe Control Center</h2>
          <p className="text-sm text-gray-400 mt-0.5">
            Every action here runs on IBM z/OS through Zowe: the backend calls Zowe CLI, which talks to z/OSMF.
          </p>
        </div>
        <MainframeNav />
        {children}
      </main>
    </div>
  );
}
