import React from "react";

const avatarColors = [
    ["#4f8ef7", "#7c3aed"], ["#22c55e", "#16a34a"], ["#f59e0b", "#d97706"],
    ["#ec4899", "#be185d"], ["#06b6d4", "#0891b2"], ["#8b5cf6", "#6d28d9"],
];

const getAvatarColor = (name: string) => avatarColors[name.charCodeAt(0) % avatarColors.length];

export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
    const colors = getAvatarColor(name);
    return (
        <div style={{
            width: size, height: size, borderRadius: "50%",
            background: `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: size * 0.38, fontWeight: 700, flexShrink: 0, color: "white",
        }}>
            {name[0]}
        </div>
    );
}
