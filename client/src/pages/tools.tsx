import { Header } from "@/components/header";

export default function ToolsPage() {
  const isAuthenticated = false;
  
  return (
    <div className="min-h-screen bg-background">
      <Header isAuthenticated={isAuthenticated} />
      <main className="mx-auto max-w-5xl px-4 py-10">
        <h2 className="text-2xl font-semibold">Tools</h2>
        <p className="mt-2 text-muted-foreground">
          Drug interactions, dosing calculators, complication protocols, and more.
        </p>
      </main>
    </div>
  );
}
