"use client";
import { useCallback } from "react";
import { Home } from "lucide-react";
import { realEstateMonitorAPI } from "@/lib/api";
import SavedIgnoredView from "@/components/shared/SavedIgnoredView";
import { REListingCard, REListingModal } from "../feed/page";

export default function RESavedPage() {
  const fetchList = useCallback(async (status) => {
    const r = await realEstateMonitorAPI.getFeed({ status, limit: 200 });
    return r.data?.items || [];
  }, []);

  return (
    <SavedIgnoredView
      title="Salvate & Ignorate"
      icon={Home}
      fetchList={fetchList}
      updateStatus={(id, status) => realEstateMonitorAPI.updateStatus(id, status)}
      deleteListing={(id) => realEstateMonitorAPI.deleteListing(id)}
      renderCard={(l, h) => <REListingCard key={l.id} listing={l} {...h} />}
      renderModal={(l, h) => <REListingModal listing={l} {...h} />}
    />
  );
}
