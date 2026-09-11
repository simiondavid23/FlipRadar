import { redirect } from "next/navigation";

// FlipRadar — MAG-1: „Produse Urmarite” fuzionata in /dashboard/products.
export default function TrackedProductsPage() {
  redirect("/dashboard/products");
}
