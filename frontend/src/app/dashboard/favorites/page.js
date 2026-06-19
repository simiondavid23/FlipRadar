import { redirect } from "next/navigation";

// FlipRadar — pagina veche "Oportunitati Salvate" fuzionata in "Produse Urmarite".
export default function FavoritesPage() {
  redirect("/dashboard/tracked-products");
}
