library(tidyverse)

files = list.files('C:/Users/kmo265/Documents/github/fisl_tundra/data/summary/pft_trajectories/no_reburn/res30m/', '.csv', full.names = TRUE)

datasets = lapply(files, read.csv)
df = do.call(rbind, datasets)

# Tidy
df_tidy = df %>%
  mutate(pft_type = gsub('_20210922_tallShrub_lidar_noRatePreds', '', pft_type)) %>%
  separate(pft_type, c('pft', 'pft_year')) %>%
  mutate(fire_year = as.numeric(fire_year),
         pft_year = as.numeric(pft_year)) %>%
  select(pft, pft_year, fire_year, land_cover, percentile, cover_value) %>%
  pivot_wider(names_from = percentile, values_from = cover_value) %>%
  mutate(lwr = mean(c(p2, p3)),
         upr = mean(c(p97, p98)),
         land_cover = recode(land_cover,
                            `10` = "Evergreen Forest",
                            `20` = "Deciduous Forest",
                            `30` = "Mixed Forest",
                            `40` = "Woodland",
                            `50` = "Low Shrub",
                            `60` = "Tall Shrub",
                            `70` = "Open Shrubs",
                            `80` = "Herbaceous",
                            `90` = "Tussock Tundra",
                            `100` = "Sparsely Vegetated",
                            `110` = "Fen",
                            `120` = "Bog",
                            `130` = "Shallows",
                            `140` = "Barren",
                            `150` = "Water",
                            `0` = "Not Available"),
        pft = recode(pft,
                     'allDecShrub' = 'Deciduous Shrubs',
                     'allEvShrub' = 'Evergreen Shrubs',
                     'allForb' = 'Forbs',
                     'graminoid' = 'Graminoids',
                     'alnshr' = 'Alder',
                     'betshr' = 'Birch',
                     'salshr' = 'Willow',
                     'decsharbs' = 'Alder, Birch, Willow',
                     'tmlichenLight2' = 'Lichen',
                     'bTree' = 'Broadleaf Trees',
                     'cTree' = 'Coniferous Trees')) %>%
  mutate(years_since_fire = pft_year-fire_year)

# Filter
df_tidy = df_tidy[!df_tidy$pft %in% c('Broadleaf Trees', 'Coniferous Trees'),]
df_tidy = df_tidy[!df_tidy$land_cover %in% c('Evergreen Forest', 'Deciduous Forest', 'Mixed Forest', 'Shallows', 'Water', 'Not Available'),]

# Establish collections
base_pfts = c('Deciduous Shrubs', 'Evergreen Shrubs', 'Forbs', 'Graminoids', 'Lichen')
shrub_genera = c('Alder', 'Birch', 'Willow')
nonwoody_plants = c('Forbs', 'Graminoids', 'Lichen')

# Plot - base PFTs
plt_base = ggplot(df_tidy[df_tidy$pft %in% base_pfts,], aes(x = years_since_fire, y = p50, color = pft, fill = pft, group = pft)) +
  stat_summary(fun.data = mean_se, geom = 'ribbon', alpha = 0.2, color = NA) +
  stat_summary(fun = mean, geom = 'line', linewidth = 1) +
  facet_wrap(~land_cover, scales = 'free') +
  geom_vline(aes(xintercept = 0), col = 'red') +
  theme_minimal(base_size = 28) +
  labs(y = 'Percent Cover', x = 'Years Since Fire', color = '', fill = '') + 
  theme(legend.position = "inside",
        legend.position.inside = c(0.75, 0.15), # Coordinates (x, y) from 0 to 1
        legend.background = element_rect(fill = "white", color = NA))
  
# Plot - nonwoody
plt_nonwoody = ggplot(df_tidy[df_tidy$pft %in% nonwoody_plants,], aes(x = years_since_fire, y = p50, color = pft, fill = pft, group = pft)) +
  stat_summary(fun.data = mean_se, geom = 'ribbon', alpha = 0.2, color = NA) +
  stat_summary(fun = mean, geom = 'line', linewidth = 1) +
  facet_wrap(~land_cover, scales = 'free') +
  geom_vline(aes(xintercept = 0), col = 'red') +
  theme_minimal(base_size = 28) +
  labs(y = 'Percent Cover', x = 'Years Since Fire', color = '', fill = '') + 
  theme(legend.position = "inside",
        legend.position.inside = c(0.75, 0.15), # Coordinates (x, y) from 0 to 1
        legend.background = element_rect(fill = "white", color = NA))

# Plot - shrub genera
plt_shrubs = ggplot(df_tidy[df_tidy$pft %in% shrub_genera,], aes(x = years_since_fire, y = p50, color = pft, fill = pft, group = pft)) +
  stat_summary(fun.data = mean_se, geom = 'ribbon', alpha = 0.2, color = NA) +
  stat_summary(fun = mean, geom = 'line', linewidth = 1) +
  facet_wrap(~land_cover, scales = 'free') +
  geom_vline(aes(xintercept = 0), col = 'red') +
  theme_minimal(base_size = 28) +
  labs(y = 'Percent Cover', x = 'Years Since Fire', color = '', fill = '') + 
  theme(legend.position = "inside",
        legend.position.inside = c(0.75, 0.15), # Coordinates (x, y) from 0 to 1
        legend.background = element_rect(fill = "white", color = NA))

ggsave('C:/Users/kmo265/Documents/github/fisl_tundra/figures/pft_trajectory_base.png',
       plt_base,
       width = 15,
       height = 10)

ggsave('C:/Users/kmo265/Documents/github/fisl_tundra/figures/pft_trajectory_nonwoody.png',
       plt_nonwoody,
       width = 15,
       height = 10)

ggsave('C:/Users/kmo265/Documents/github/fisl_tundra/figures/pft_trajectory_shrubs.png',
       plt_shrubs,
       width = 15,
       height = 10)