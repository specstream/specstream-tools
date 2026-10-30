import { useColorScheme } from "@airtable/blocks/ui";

export type Palette = {
	ink: string;
	mark: boolean;
	panel: string;
	token: string;
	tokenNew: string;
	note: string;
	errorBg: string;
	errorBorder: string;
	errorText: string;
	accent: string;
	field: string;
};

const LIGHT: Palette = {
	ink: "#242722",
	mark: false,
	panel: "#fafaf7",
	token: "#ffffff",
	tokenNew: "#eaf0fa",
	note: "#f3f2ee",
	errorBg: "#fdeeec",
	errorBorder: "#f2c9c2",
	errorText: "#7a2416",
	accent: "#2558a8",
	field: "rgba(0,0,0,0.05)",
};

const DARK: Palette = {
	ink: "#f5f0e6",
	mark: true,
	panel: "rgba(255,255,255,0.04)",
	token: "rgba(255,255,255,0.06)",
	tokenNew: "rgba(128,172,240,0.18)",
	note: "rgba(255,255,255,0.06)",
	errorBg: "rgba(172,78,53,0.18)",
	errorBorder: "rgba(172,78,53,0.5)",
	errorText: "#f3c2b5",
	accent: "#80acf0",
	field: "rgba(255,255,255,0.08)",
};

export function usePalette(): Palette {
	return useColorScheme().colorScheme === "dark" ? DARK : LIGHT;
}
