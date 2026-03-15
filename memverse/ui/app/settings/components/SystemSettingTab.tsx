"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SaveIcon, RotateCcw } from "lucide-react";
import { FormView } from "@/components/form-view";
import { JsonEditor } from "@/components/json-editor";
import { useConfig } from "@/hooks/useConfig";
import { useSelector } from "react-redux";
import { RootState } from "@/store/store";
import { useToast } from "@/components/ui/use-toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export function SystemSettingTab() {
  const { toast } = useToast();
  const configState = useSelector((state: RootState) => state.config);
  const [settings, setSettings] = useState({
    memverse: configState.memverse || { custom_instructions: null },
    mem0: configState.mem0,
  });
  const [viewMode, setViewMode] = useState<"form" | "json">("form");
  const { fetchConfig, saveConfig, resetConfig, isLoading } = useConfig();

  useEffect(() => {
    const loadConfig = async () => {
      try { await fetchConfig(); }
      catch { toast({ title: "Error", description: "Failed to load configuration", variant: "destructive" }); }
    };
    loadConfig();
  }, []);

  useEffect(() => {
    setSettings((prev) => ({
      ...prev,
      memverse: configState.memverse || { custom_instructions: null },
      mem0: configState.mem0,
    }));
  }, [configState.memverse, configState.mem0]);

  const handleSave = async () => {
    try {
      await saveConfig({ memverse: settings.memverse, mem0: settings.mem0 });
      toast({ title: "Settings saved", description: "Your configuration has been updated successfully." });
    } catch { toast({ title: "Error", description: "Failed to save configuration", variant: "destructive" }); }
  };

  const handleReset = async () => {
    try {
      await resetConfig();
      toast({ title: "Settings reset", description: "Configuration has been reset to default values." });
      await fetchConfig();
    } catch { toast({ title: "Error", description: "Failed to reset configuration", variant: "destructive" }); }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">System Setting</h2>
          <p className="text-sm text-zinc-400 mt-1">Manage Memverse and Mem0 configuration</p>
        </div>
        <div className="flex space-x-2">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" className="border-zinc-800 text-zinc-200 hover:bg-zinc-700 hover:text-zinc-50" disabled={isLoading}>
                <RotateCcw className="mr-2 h-4 w-4" /> Reset Defaults
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reset Configuration?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will reset all settings to the system defaults. Any custom configuration will be lost.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleReset} className="bg-red-600 hover:bg-red-700">Reset</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button onClick={handleSave} className="bg-primary hover:bg-primary/90" disabled={isLoading}>
            <SaveIcon className="mr-2 h-4 w-4" /> {isLoading ? "Saving..." : "Save Configuration"}
          </Button>
        </div>
      </div>

      <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as "form" | "json")} className="w-full">
        <TabsList className="grid w-full grid-cols-2 mb-6">
          <TabsTrigger value="form">Form View</TabsTrigger>
          <TabsTrigger value="json">JSON Editor</TabsTrigger>
        </TabsList>
        <TabsContent value="form">
          <FormView settings={settings} onChange={setSettings} />
        </TabsContent>
        <TabsContent value="json">
          <Card>
            <CardHeader>
              <CardTitle>JSON Configuration</CardTitle>
              <CardDescription>Edit the entire configuration directly as JSON</CardDescription>
            </CardHeader>
            <CardContent>
              <JsonEditor value={settings} onChange={setSettings} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
