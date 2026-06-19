import { redirect } from "next/navigation";

// FlipRadar — pagina veche "Radar Preturi" fuzionata in "Produse Urmarite".
export default function WatchlistPage() {
  redirect("/dashboard/tracked-products");
}
