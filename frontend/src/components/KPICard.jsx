export function KPICard({
  title,
  value,
  icon: Icon,
  subtext,
  iconBg = "#fff7ed",
  iconColor = "#ea580c",
  accentColor,
}) {
  return (
    <div className="kpi-card" style={accentColor ? { borderTop: `3px solid ${accentColor}` } : {}}>
      <div className="kpi-header">
        <span className="kpi-title">{title}</span>
        {Icon && (
          <div className="kpi-icon-wrap" style={{ backgroundColor: iconBg, color: iconColor }}>
            <Icon size={17} />
          </div>
        )}
      </div>
      <div className="kpi-value">{value}</div>
      {subtext && <div className="kpi-subtext">{subtext}</div>}
    </div>
  );
}
