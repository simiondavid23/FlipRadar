"use client";
import { useCallback, useEffect, useState } from "react";
import { Radar } from "lucide-react";
import { radarAPI } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ListingFeedCard from "@/components/shared/ListingFeedCard";
import ListingDetailModal from "@/components/shared/ListingDetailModal";
import SavedIgnoredView from "@/components/shared/SavedIgnoredView";
import {
  SCORE_COLORS, PLATFORM_COLORS, PLATFORM_LABELS, SCORE_EXPLANATIONS,
  RadarDetailBanner,
} from "../page";

const scoreCfgOf = (s) => SCORE_COLORS[s] || { bg: "rgba(100,116,139,0.15)", border: "#64748b", text: "#94a3b8" };
const platformCfgOf = (p) => PLATFORM_COLORS[p] || PLATFORM_COLORS.olx;
const openLabelOf = (p) => PLATFORM_LABELS[p?.toLowerCase()] || "Deschide anunțul";

// Modal identic cu feed-ul Radar (review AI + șabloane + ML + detaliu on-demand Vinted/FB),
// cu detaliul îmbogățit ținut local (nu mutăm starea paginii-feed).
function RadarSavedModal({ listing, onClose, onSave, onIgnore, templates, reviewEnabled }) {
  const [detail, setDetail] = useState(listing);
  const [generatingAI, setGeneratingAI] = useState(false);
  useEffect(() => { setDetail(listing); }, [listing.id]);

  const generateAI = async () => {
    setGeneratingAI(true);
    try {
      const r = await radarAPI.generateListingAIReview(listing.id);
      setDetail((d) => ({ ...d, ai_review: r.data.ai_review }));
    } catch (e) { alert(e.response?.data?.detail || "Nu am putut genera review-ul."); }
    finally { setGeneratingAI(false); }
  };
  const loadVintedDetail = async (id) => {
    try { const r = await radarAPI.getVintedDetail(id); setDetail((d) => ({ ...d, ...r.data })); return !!r.data.vinted_detail_fetched; }
    catch { return false; }
  };
  const loadFacebookDetail = async (id) => {
    try { const r = await radarAPI.getFacebookDetail(id); setDetail((d) => ({ ...d, ...r.data })); return !!r.data.facebook_detail_fetched; }
    catch { return false; }
  };

  return (
    <ListingDetailModal
      listing={detail}
      images={detail.images || []}
      scoreCfg={scoreCfgOf(detail.score)}
      scoreBadge={detail.score}
      scoreExplanation={SCORE_EXPLANATIONS[detail.score]}
      platformCfg={platformCfgOf(detail.platform)}
      platformBadge={detail.platform}
      platformUpper={detail.platform?.toUpperCase()}
      openLabel={openLabelOf(detail.platform)}
      onClose={onClose}
      onSave={onSave}
      onIgnore={onIgnore}
      showReview
      reviewEnabled={reviewEnabled}
      onGenerateAI={generateAI}
      generatingAI={generatingAI}
      reviewSettingsHref="/dashboard/settings"
      showTemplates
      templates={templates}
      onRenderTemplate={radarAPI.renderTemplate}
      templatesHref="/dashboard/settings"
      detailBannerSlot={<RadarDetailBanner listing={detail} onLoadVintedDetail={loadVintedDetail} onLoadFacebookDetail={loadFacebookDetail} />}
    />
  );
}

export default function RadarSavedPage() {
  const { user } = useAuth();
  const reviewEnabled = user?.ai_features_config?.ai_radar_review !== false;
  const [templates, setTemplates] = useState([]);
  useEffect(() => { radarAPI.getTemplates().then((r) => setTemplates(r.data || [])).catch(() => {}); }, []);

  const fetchList = useCallback(async (status) => {
    const r = await radarAPI.getListings({ status, per_page: 200 });
    return r.data?.items || [];
  }, []);

  return (
    <SavedIgnoredView
      title="Salvate & Ignorate"
      icon={Radar}
      fetchList={fetchList}
      updateStatus={(id, status) => radarAPI.updateListingStatus(id, status)}
      deleteListing={(id) => radarAPI.deleteListing(id)}
      renderCard={(l, h) => (
        <ListingFeedCard
          key={l.id}
          listing={l}
          scoreCfg={scoreCfgOf(l.score)}
          scoreBadge={l.score}
          platformCfg={platformCfgOf(l.platform)}
          platformBadge={l.platform}
          image={l.images?.[0]}
          openLabel={openLabelOf(l.platform)}
          onOpen={h.onOpen}
          onSave={h.onSave}
          onIgnore={h.onIgnore}
          onDelete={h.onDelete}
          isSelected={h.isSelected}
          onToggleSelect={h.onToggleSelect}
        />
      )}
      renderModal={(l, h) => <RadarSavedModal listing={l} {...h} templates={templates} reviewEnabled={reviewEnabled} />}
    />
  );
}
