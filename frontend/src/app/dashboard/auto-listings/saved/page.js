"use client";
import { useCallback } from "react";
import { Car } from "lucide-react";
import { autoListingsAPI } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import SavedIgnoredView from "@/components/shared/SavedIgnoredView";
import { AutoListingCard, AutoListingModal } from "../feed/page";

export default function AutoSavedPage() {
  const { user } = useAuth();
  const reviewEnabled = user?.ai_features_config?.ai_radar_review !== false;

  const fetchList = useCallback(async (status) => {
    const r = await autoListingsAPI.getFeed({ status, limit: 200 });
    return r.data?.items || [];
  }, []);

  return (
    <SavedIgnoredView
      title="Salvate & Ignorate"
      icon={Car}
      breadcrumb={["AUTO ANUNȚURI", "SALVATE"]}
      fetchList={fetchList}
      updateStatus={(id, status) => autoListingsAPI.updateStatus(id, status)}
      deleteListing={(id) => autoListingsAPI.deleteListing(id)}
      renderCard={(l, h) => <AutoListingCard key={l.id} listing={l} {...h} />}
      renderModal={(l, h) => <AutoListingModal listing={l} {...h} reviewEnabled={reviewEnabled} />}
    />
  );
}
